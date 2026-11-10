"""V3 accuracy push: richer lexical+ngram features, LightGBM/CatBoost, soft-vote & stacking.

Usage: python train_v3.py STAGE [STAGE ...]
Stages: ablatesingle ensemble stack select final verify

Protocol (unchanged): seed 42, frozen 70/15/15 split from V2, validation for selection,
test set used once. No scheme/www leakage features.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import time
import traceback
from datetime import datetime
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

from src.data import CLASSES, SEED
from src.features import hostname
from src.features_v2 import FEATURE_NAMES_V2
from src.features_v3 import FEATURE_NAMES_V3_LEXICAL
from src.runinfo import environment, peak_memory_mb

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts" / "v3"
ART_V2 = ROOT / "artifacts" / "v2"
RES = ROOT / "results" / "v3"
RES_V2 = ROOT / "results" / "v2"
TRIALS = RES / "model_trials_val.csv"

MALICIOUS = ["defacement", "malware", "phishing"]
V2_TEST = {"accuracy": 0.9089, "macro_f1": 0.8863, "recall_phishing": 0.7559}
TIE_F1 = 0.005
N_CLASSES = len(CLASSES)

# Strong single-model defaults (V2 winner geometry + modest ngram capacity).
XGB_PARAMS = {
    "max_depth": 10,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
}
LGBM_PARAMS = {
    "num_leaves": 128,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_samples": 40,
}
CAT_PARAMS = {
    "depth": 8,
    "learning_rate": 0.08,
    "l2_leaf_reg": 3.0,
}

METRIC_COLS = (
    ["accuracy", "macro_precision", "macro_recall", "macro_f1",
     "weighted_precision", "weighted_recall", "weighted_f1"]
    + [f"{m}_{c}" for c in CLASSES for m in ("precision", "recall", "f1", "support")]
    + ["unseen_host_n", "unseen_host_accuracy", "unseen_host_macro_f1", "confusion_matrix"]
)
COLUMNS = (
    ["trial_id", "stage", "family", "feature_set", "n_features", "weight_mode",
     "params", "extra", "status", "error", "fit_s", "predict_s",
     "peak_memory_mb", "timestamp"] + METRIC_COLS
)


# ---------------------------------------------------------------- data

class Data:
    def __init__(self):
        self.df = pd.read_parquet(ART / "clean.parquet")
        self.x_lex = pd.read_parquet(ART / "features_v3_lexical.parquet")
        self.x_full = pd.read_parquet(ART / "features_v3_full.parquet")
        with open(ART / "feature_manifest.json") as f:
            self.manifest = json.load(f)

        assert self.x_lex.index.equals(self.df.index)
        assert self.x_full.index.equals(self.df.index)
        assert list(self.x_lex.columns) == FEATURE_NAMES_V3_LEXICAL

        # Optional V2 matrix for ablation.
        self.x_v2 = None
        if (ART_V2 / "features_v2_norm.parquet").exists():
            self.x_v2 = pd.read_parquet(ART_V2 / "features_v2_norm.parquet")
            assert self.x_v2.index.equals(self.df.index)

        self.enc = LabelEncoder().fit(CLASSES)
        assert list(self.enc.classes_) == CLASSES
        self.y = self.enc.transform(self.df["label"])
        split = self.df["split"].to_numpy()
        self.tr = split == "train"
        self.va = split == "val"
        self.te = split == "test"
        self.trva = self.tr | self.va
        assert not (self.tr & self.va).any() and not (self.trva & self.te).any()

        self.hosts = self.df["url_norm"].map(hostname).to_numpy()
        train_hosts = set(self.hosts[self.tr])
        self.va_unseen = ~pd.Series(self.hosts[self.va]).isin(train_hosts).to_numpy()

    def features(self, feature_set: str) -> pd.DataFrame:
        if feature_set == "v2_full":
            if self.x_v2 is None:
                raise SystemExit("V2 features missing for ablation.")
            return self.x_v2[FEATURE_NAMES_V2]
        if feature_set == "v3_lexical":
            return self.x_lex
        if feature_set == "v3_full":
            return self.x_full
        raise ValueError(feature_set)


# ---------------------------------------------------------------- metrics / bookkeeping

def class_weights(y, mode):
    if mode == "none":
        return None
    counts = np.bincount(y, minlength=N_CLASSES)
    base = len(y) / (N_CLASSES * counts)
    power = {"sqrt_balanced": 0.5, "balanced": 1.0}[mode]
    return {int(k): float(w ** power) for k, w in enumerate(base)}


def row_weights(y, cw):
    return None if cw is None else np.array([cw[int(k)] for k in y], dtype=np.float64)


def evaluate(y_true, y_pred, unseen=None):
    labels = list(range(N_CLASSES))
    out = {"accuracy": accuracy_score(y_true, y_pred)}
    for avg in ("macro", "weighted"):
        p, r, f, _ = precision_recall_fscore_support(
            y_true, y_pred, average=avg, zero_division=0)
        out.update({f"{avg}_precision": p, f"{avg}_recall": r, f"{avg}_f1": f})
    p, r, f, s = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0)
    for i, c in enumerate(CLASSES):
        out.update({
            f"precision_{c}": p[i], f"recall_{c}": r[i], f"f1_{c}": f[i], f"support_{c}": s[i],
        })
    out = {k: round(float(v), 4) if not k.startswith("support") else int(v)
           for k, v in out.items()}
    if unseen is not None:
        out["unseen_host_n"] = int(unseen.sum())
        out["unseen_host_accuracy"] = round(
            float(accuracy_score(y_true[unseen], y_pred[unseen])), 4)
        out["unseen_host_macro_f1"] = round(float(precision_recall_fscore_support(
            y_true[unseen], y_pred[unseen], average="macro", zero_division=0)[2]), 4)
    out["confusion_matrix"] = json.dumps(
        confusion_matrix(y_true, y_pred, labels=labels).tolist())
    return out


def order_by_rule(df):
    df = df.assign(min_malicious_recall=df[[f"recall_{c}" for c in MALICIOUS]].min(axis=1))
    remaining = df.copy()
    ordered = []
    while len(remaining):
        near = remaining[remaining["macro_f1"] >= remaining["macro_f1"].max() - TIE_F1]
        pick = near.sort_values(
            ["accuracy", "min_malicious_recall", "fit_s"],
            ascending=[False, False, True],
        ).index[0]
        ordered.append(pick)
        remaining = remaining.drop(index=pick)
    return df.loc[ordered]


def load_trials():
    return pd.read_csv(TRIALS) if TRIALS.exists() else pd.DataFrame(columns=COLUMNS)


def append_trial(row):
    frame = pd.DataFrame([row]).reindex(columns=COLUMNS)
    frame.to_csv(TRIALS, mode="a", header=not TRIALS.exists(), index=False)


def ok_trials(stages=None):
    df = load_trials()
    df = df[df["status"] == "ok"]
    if stages is not None:
        df = df[df["stage"].isin(stages)]
    return df.drop_duplicates("trial_id", keep="last")


# ---------------------------------------------------------------- model builders

def _as_numpy(X):
    return X.to_numpy(dtype=np.float32, copy=False) if hasattr(X, "to_numpy") else np.asarray(X, dtype=np.float32)


def fit_xgb(X, y, cw, X_val=None, y_val=None, n_estimators=None, params=None):
    params = {**(params or XGB_PARAMS)}
    sw = row_weights(y, cw)
    Xn, yn = _as_numpy(X), np.asarray(y)
    # Prefer CUDA when available (RTX 2060 Super); fall back to CPU hist.
    device = "cuda"
    common = dict(
        objective="multi:softprob", eval_metric="mlogloss",
        tree_method="hist", device=device, n_jobs=-1, random_state=SEED, **params,
    )
    try:
        if n_estimators is None:
            model = XGBClassifier(n_estimators=1200, early_stopping_rounds=50, **common)
            model.fit(Xn, yn, sample_weight=sw,
                      eval_set=[(_as_numpy(X_val), np.asarray(y_val))], verbose=False)
            return model, {
                "best_iteration": int(model.best_iteration),
                "n_estimators_used": int(model.best_iteration) + 1,
                "best_val_mlogloss": round(float(model.best_score), 5),
                "device": device,
            }
        model = XGBClassifier(n_estimators=n_estimators, **common)
        model.fit(Xn, yn, sample_weight=sw, verbose=False)
        return model, {"n_estimators_used": n_estimators, "device": device}
    except Exception as exc:
        print(f"[warn] XGB device={device} failed ({exc}); falling back to CPU", flush=True)
        device = "cpu"
        common["device"] = device
        if n_estimators is None:
            model = XGBClassifier(n_estimators=1200, early_stopping_rounds=50, **common)
            model.fit(Xn, yn, sample_weight=sw,
                      eval_set=[(_as_numpy(X_val), np.asarray(y_val))], verbose=False)
            return model, {
                "best_iteration": int(model.best_iteration),
                "n_estimators_used": int(model.best_iteration) + 1,
                "best_val_mlogloss": round(float(model.best_score), 5),
                "device": device,
            }
        model = XGBClassifier(n_estimators=n_estimators, **common)
        model.fit(Xn, yn, sample_weight=sw, verbose=False)
        return model, {"n_estimators_used": n_estimators, "device": device}


def fit_lgbm(X, y, cw, X_val=None, y_val=None, n_estimators=None, params=None):
    params = {**(params or LGBM_PARAMS)}
    sw = row_weights(y, cw)
    Xn, yn = _as_numpy(X), np.asarray(y)
    if n_estimators is None:
        model = lgb.LGBMClassifier(
            n_estimators=2000, objective="multiclass", num_class=N_CLASSES,
            n_jobs=-1, random_state=SEED, verbosity=-1, **params,
        )
        Xv, yv = _as_numpy(X_val), np.asarray(y_val)
        model.fit(
            Xn, yn, sample_weight=sw,
            eval_set=[(Xv, yv)],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
        )
        used = int(model.best_iteration_) if model.best_iteration_ else model.n_estimators
        return model, {"n_estimators_used": used, "best_iteration": used}
    model = lgb.LGBMClassifier(
        n_estimators=n_estimators, objective="multiclass", num_class=N_CLASSES,
        n_jobs=-1, random_state=SEED, verbosity=-1, **params,
    )
    model.fit(Xn, yn, sample_weight=sw)
    return model, {"n_estimators_used": n_estimators}


def fit_cat(X, y, cw, X_val=None, y_val=None, n_estimators=None, params=None):
    """CatBoost on float32 numpy; capped iterations to avoid multi-hour stalls on wide matrices."""
    params = {**(params or CAT_PARAMS)}
    class_w = None if cw is None else [cw[i] for i in range(N_CLASSES)]
    Xn, yn = _as_numpy(X), np.asarray(y)
    thread_count = max(1, min(8, (os.cpu_count() or 8)))
    if n_estimators is None:
        model = CatBoostClassifier(
            iterations=800, loss_function="MultiClass", eval_metric="MultiClass",
            random_seed=SEED, thread_count=thread_count, verbose=False,
            early_stopping_rounds=40, class_weights=class_w,
            allow_writing_files=False, **params,
        )
        Xv, yv = _as_numpy(X_val), np.asarray(y_val)
        model.fit(Xn, yn, eval_set=(Xv, yv), use_best_model=True)
        used = int(model.best_iteration_) + 1 if model.best_iteration_ is not None else int(model.tree_count_)
        return model, {"n_estimators_used": int(used), "best_iteration": int(used)}
    model = CatBoostClassifier(
        iterations=n_estimators, loss_function="MultiClass",
        random_seed=SEED, thread_count=thread_count, verbose=False,
        class_weights=class_w, allow_writing_files=False, **params,
    )
    model.fit(Xn, yn)
    return model, {"n_estimators_used": n_estimators}


def fit_family(family, X, y, weight_mode, X_val=None, y_val=None, n_estimators=None):
    cw = class_weights(y, weight_mode)
    if family == "xgb":
        return fit_xgb(X, y, cw, X_val, y_val, n_estimators)
    if family == "lgbm":
        return fit_lgbm(X, y, cw, X_val, y_val, n_estimators)
    if family == "cat":
        return fit_cat(X, y, cw, X_val, y_val, n_estimators)
    raise ValueError(family)


def predict_proba(model, X):
    Xn = _as_numpy(X)
    return np.asarray(model.predict_proba(Xn), dtype=np.float64)


# ---------------------------------------------------------------- trials

def run_single_trial(data, trial_id, stage, family, feature_set, weight_mode):
    done = load_trials()
    prior = done[(done["trial_id"] == trial_id) & (done["status"] == "ok")]
    if len(prior):
        print(f"[skip] {trial_id}")
        return prior.iloc[-1].to_dict()

    X = data.features(feature_set)
    row = {
        "trial_id": trial_id, "stage": stage, "family": family,
        "feature_set": feature_set, "n_features": X.shape[1],
        "weight_mode": weight_mode,
        "params": json.dumps({"xgb": XGB_PARAMS, "lgbm": LGBM_PARAMS, "cat": CAT_PARAMS}[
            {"xgb": "xgb", "lgbm": "lgbm", "cat": "cat"}[family]]),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    model = None
    t0 = time.perf_counter()
    try:
        model, extra = fit_family(
            family, X[data.tr], data.y[data.tr], weight_mode,
            X_val=X[data.va], y_val=data.y[data.va],
        )
        row["fit_s"] = round(time.perf_counter() - t0, 1)
        t1 = time.perf_counter()
        proba = predict_proba(model, X[data.va])
        pred = proba.argmax(axis=1)
        row["predict_s"] = round(time.perf_counter() - t1, 1)
        row.update(evaluate(data.y[data.va], pred, data.va_unseen))
        row.update({"status": "ok", "extra": json.dumps(extra), "error": ""})
        # Cache val probabilities for stacking/softvote.
        np.save(ART / f"val_proba_{trial_id}.npy", proba)
        joblib.dump({"model": model, "feature_set": feature_set, "family": family,
                     "weight_mode": weight_mode, "extra": extra},
                    ART / f"model_{trial_id}.joblib")
    except Exception as exc:
        row.update({
            "status": "failed", "error": f"{type(exc).__name__}: {exc}",
            "fit_s": round(time.perf_counter() - t0, 1), "extra": "{}",
        })
        traceback.print_exc()
    row["peak_memory_mb"] = peak_memory_mb()
    append_trial(row)
    del model
    gc.collect()
    print({k: row.get(k) for k in (
        "trial_id", "status", "accuracy", "macro_f1", "recall_phishing",
        "unseen_host_accuracy", "fit_s")}, flush=True)
    return row


# ---------------------------------------------------------------- stages

def stage_ablatesingle(data):
    """Feature ablation with the V2-winning XGB geometry + strongest single V3 models."""
    run_single_trial(data, "xgb_v2_full_ref", "ablate", "xgb", "v2_full", "sqrt_balanced")
    run_single_trial(data, "xgb_v3_lexical", "ablate", "xgb", "v3_lexical", "sqrt_balanced")
    run_single_trial(data, "xgb_v3_full", "ablate", "xgb", "v3_full", "sqrt_balanced")
    rows = ok_trials(["ablate"])
    cols = ["trial_id", "feature_set", "n_features", "accuracy", "macro_f1",
            *[f"recall_{c}" for c in CLASSES], "unseen_host_accuracy", "fit_s"]
    print(order_by_rule(rows)[cols].to_string(index=False))


def stage_ensemble(data):
    """Train complementary GBDT families on the full V3 feature set."""
    for family, tid in (("lgbm", "lgbm_v3_full"), ("cat", "cat_v3_full"),
                        ("xgb", "xgb_v3_full")):
        # xgb_v3_full may already exist from ablatesingle.
        run_single_trial(data, tid, "ensemble", family, "v3_full", "sqrt_balanced")
    rows = ok_trials(["ablate", "ensemble"])
    cols = ["trial_id", "family", "accuracy", "macro_f1", "recall_phishing", "fit_s"]
    print(order_by_rule(rows)[cols].to_string(index=False))


def _load_val_proba(trial_id):
    path = ART / f"val_proba_{trial_id}.npy"
    if not path.exists():
        raise SystemExit(f"Missing {path}; run ensemble/ablate stages first.")
    return np.load(path)


def _softvote_trial(data, trial_id, base_ids):
    done = load_trials()
    if len(done[(done["trial_id"] == trial_id) & (done["status"] == "ok")]):
        print(f"[skip] {trial_id}")
        return
    for b in base_ids:
        if not (ART / f"val_proba_{b}.npy").exists():
            raise SystemExit(f"Missing val proba for {b}.")
    avg = np.mean([_load_val_proba(b) for b in base_ids], axis=0)
    pred = avg.argmax(axis=1)
    row = {
        "trial_id": trial_id, "stage": "stack", "family": "softvote",
        "feature_set": "v3_full", "n_features": data.x_full.shape[1],
        "weight_mode": "sqrt_balanced",
        "params": json.dumps({"bases": base_ids, "method": "mean_proba"}),
        "extra": json.dumps({"bases": base_ids}),
        "status": "ok", "error": "", "fit_s": 0.0,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "peak_memory_mb": peak_memory_mb(),
    }
    t0 = time.perf_counter()
    row.update(evaluate(data.y[data.va], pred, data.va_unseen))
    row["predict_s"] = round(time.perf_counter() - t0, 1)
    np.save(ART / f"val_proba_{trial_id}.npy", avg)
    append_trial(row)
    print({k: row.get(k) for k in (
        "trial_id", "accuracy", "macro_f1", "recall_phishing")}, flush=True)


def stage_stack(data):
    """Soft-vote (+ optional logistic stacking) over strong base learners only."""
    candidates = [tid for tid in ("xgb_v3_full", "lgbm_v3_full", "cat_v3_full")
                  if (ART / f"val_proba_{tid}.npy").exists()]
    if len(candidates) < 2:
        raise SystemExit(f"Need >=2 base val probas for stacking; have {candidates}")

    trials = ok_trials().set_index("trial_id")
    best_acc = max(float(trials.loc[tid, "accuracy"]) for tid in candidates)
    # Drop clearly weaker bases (e.g. under-tuned CatBoost) so they cannot dilute the vote.
    available = [tid for tid in candidates
                 if float(trials.loc[tid, "accuracy"]) >= best_acc - 0.01]
    print(f"Stack bases kept: {available} (best_acc={best_acc:.4f})", flush=True)
    if len(available) < 2:
        available = candidates[:2]

    _softvote_trial(data, "softvote_" + "_".join(t.split("_")[0] for t in available), available)
    if set(available) >= {"xgb_v3_full", "lgbm_v3_full"}:
        _softvote_trial(data, "softvote_xgb_lgbm", ["xgb_v3_full", "lgbm_v3_full"])

    families = []
    if "xgb_v3_full" in available:
        families.append("xgb")
    if "lgbm_v3_full" in available:
        families.append("lgbm")
    if "cat_v3_full" in available:
        families.append("cat")

    tid = "stack_lr_" + "_".join(families)
    done = load_trials()
    if len(done[(done["trial_id"] == tid) & (done["status"] == "ok")]):
        print(f"[skip] {tid}")
        return

    # Faster 3-fold OOF stacking (still leak-free w.r.t. val/test).
    X = data.features("v3_full")
    y_tr = data.y[data.tr]
    X_tr, X_va = X[data.tr], X[data.va]
    cw_mode = "sqrt_balanced"
    oof = {fam: np.zeros((X_tr.shape[0], N_CLASSES), dtype=np.float64) for fam in families}
    val_base = {}
    fold_extras = []
    skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=SEED)
    t0 = time.perf_counter()
    for fold, (idx_a, idx_b) in enumerate(skf.split(X_tr, y_tr), 1):
        print(f"  stack fold {fold}/3 families={families}", flush=True)
        X_a, X_b = X_tr.iloc[idx_a], X_tr.iloc[idx_b]
        y_a, y_b = y_tr[idx_a], y_tr[idx_b]
        for fam in families:
            model, extra = fit_family(fam, X_a, y_a, cw_mode, X_val=X_b, y_val=y_b)
            oof[fam][idx_b] = predict_proba(model, X_b)
            fold_extras.append({"fold": fold, "family": fam, **extra})
            del model
            gc.collect()

    base_models = {}
    for fam in families:
        print(f"  refit base {fam} on full train", flush=True)
        model, extra = fit_family(
            fam, X_tr, y_tr, cw_mode, X_val=X_va, y_val=data.y[data.va])
        base_models[fam] = model
        val_base[fam] = predict_proba(model, X_va)
        fold_extras.append({"fold": "full_train", "family": fam, **extra})

    meta_X_tr = np.hstack([oof[f] for f in families])
    meta_X_va = np.hstack([val_base[f] for f in families])
    meta = LogisticRegression(max_iter=2000, solver="lbfgs", random_state=SEED, C=1.0)
    meta.fit(meta_X_tr, y_tr)
    fit_s = round(time.perf_counter() - t0, 1)
    t1 = time.perf_counter()
    proba = meta.predict_proba(meta_X_va)
    pred = proba.argmax(axis=1)
    predict_s = round(time.perf_counter() - t1, 1)

    row = {
        "trial_id": tid, "stage": "stack", "family": "stack_lr",
        "feature_set": "v3_full", "n_features": X.shape[1],
        "weight_mode": cw_mode,
        "params": json.dumps({"bases": families, "meta": "LogisticRegression(C=1)", "oof_folds": 3}),
        "extra": json.dumps({"fold_extras": [e for e in fold_extras if e["fold"] == "full_train"]}),
        "status": "ok", "error": "", "fit_s": fit_s, "predict_s": predict_s,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "peak_memory_mb": peak_memory_mb(),
    }
    row.update(evaluate(data.y[data.va], pred, data.va_unseen))
    np.save(ART / f"val_proba_{tid}.npy", proba)
    joblib.dump(
        {"meta": meta, "families": families, "feature_set": "v3_full", "weight_mode": cw_mode},
        ART / f"model_{tid}.joblib",
    )
    for fam, model in base_models.items():
        joblib.dump(model, ART / f"stack_base_train_{fam}.joblib")
    append_trial(row)
    print({k: row.get(k) for k in (
        "trial_id", "accuracy", "macro_f1", "recall_phishing", "fit_s")}, flush=True)


def stage_select(data):
    trials = ok_trials(["ablate", "ensemble", "stack"])
    trials = order_by_rule(trials)
    cols = ["trial_id", "family", "feature_set", "n_features", "accuracy",
            "macro_precision", "macro_recall", "macro_f1",
            *[f"recall_{c}" for c in CLASSES], "unseen_host_accuracy",
            "unseen_host_macro_f1", "fit_s"]
    trials[cols].to_csv(RES / "model_trials_ranked_val.csv", index=False)

    # Prefer full V3 feature models; still report lexical-only / v2 ablations.
    pool = trials[trials["feature_set"] == "v3_full"]
    if pool.empty:
        pool = trials
    winner = order_by_rule(pool).iloc[0]
    selection = {
        "winner": {k: winner[k] for k in (
            "trial_id", "family", "feature_set", "weight_mode", "n_features")},
        "winner_params": json.loads(winner["params"]) if isinstance(winner["params"], str)
        else winner["params"],
        "winner_extra": json.loads(winner["extra"]) if isinstance(winner["extra"], str)
        else winner["extra"],
        "winner_val_metrics": {k: winner[k] for k in METRIC_COLS if k != "confusion_matrix"},
        "rule": ("max macro-F1 on validation; within 0.005 prefer higher accuracy, then "
                 "higher min malicious recall, then lower fit time; prefer feature_set=v3_full"),
        "v2_test_reference": V2_TEST,
        "ranked_top10": order_by_rule(trials).head(10)[
            ["trial_id", "family", "feature_set", "accuracy", "macro_f1",
             "recall_phishing"]].to_dict("records"),
        "selected_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(RES / "selection.json", "w") as f:
        json.dump(selection, f, indent=2, default=str)
    print(order_by_rule(trials)[cols[:8] + ["recall_phishing"]].head(10).to_string(index=False))
    print("Winner:", selection["winner"])


def _refit_single(data, family, feature_set, weight_mode, n_estimators):
    X = data.features(feature_set)
    model, extra = fit_family(
        family, X[data.trva], data.y[data.trva], weight_mode, n_estimators=n_estimators)
    return model, extra, X


def _refit_softvote(data, base_ids, weight_mode="sqrt_balanced"):
    X = data.features("v3_full")
    bases = {}
    blocks = []
    extras = {}
    prior = ok_trials().set_index("trial_id")
    fam_of = {"xgb_v3_full": "xgb", "lgbm_v3_full": "lgbm", "cat_v3_full": "cat"}
    for tid in base_ids:
        fam = fam_of[tid]
        n_est = json.loads(prior.loc[tid, "extra"])["n_estimators_used"]
        print(f"  softvote refit {fam} trees={n_est}", flush=True)
        model, extra = fit_family(
            fam, X[data.trva], data.y[data.trva], weight_mode, n_estimators=int(n_est))
        bases[fam] = model
        blocks.append(predict_proba(model, X[data.te]))
        extras[fam] = extra
    proba = np.mean(blocks, axis=0)
    return proba, {"bases": bases, "extras": extras, "feature_set": "v3_full",
                   "weight_mode": weight_mode, "method": "mean_proba",
                   "families": [fam_of[t] for t in base_ids]}, X


def _refit_stack(data, families, weight_mode="sqrt_balanced"):
    """OOF on train+val for meta; bases refit on train+val for test prediction."""
    X = data.features("v3_full")
    y = data.y[data.trva]
    X_trva = X[data.trva]
    X_te = X[data.te]

    oof = {fam: np.zeros((X_trva.shape[0], N_CLASSES), dtype=np.float64) for fam in families}
    skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=SEED)
    extras = []
    for fold, (idx_a, idx_b) in enumerate(skf.split(X_trva, y), 1):
        print(f"  final stack fold {fold}/3", flush=True)
        for fam in families:
            model, extra = fit_family(
                fam, X_trva.iloc[idx_a], y[idx_a], weight_mode,
                X_val=X_trva.iloc[idx_b], y_val=y[idx_b])
            oof[fam][idx_b] = predict_proba(model, X_trva.iloc[idx_b])
            extras.append({"fold": fold, "family": fam, **extra})
            del model
            gc.collect()

    meta = LogisticRegression(max_iter=2000, solver="lbfgs", random_state=SEED, C=1.0)
    meta.fit(np.hstack([oof[f] for f in families]), y)

    bases = {}
    test_blocks = []
    for fam in families:
        print(f"  final refit base {fam}", flush=True)
        used = [e["n_estimators_used"] for e in extras if e["family"] == fam]
        n_est = int(np.median(used)) if used else None
        model, extra = fit_family(fam, X_trva, y, weight_mode, n_estimators=n_est)
        bases[fam] = model
        test_blocks.append(predict_proba(model, X_te))
        extras.append({"fold": "full_trva", "family": fam, **extra})

    proba = meta.predict_proba(np.hstack(test_blocks))
    bundle = {"meta": meta, "bases": bases, "families": families,
              "feature_set": "v3_full", "weight_mode": weight_mode, "extras": extras}
    return proba, bundle, X


def stage_final(data):
    if (RES / "test_metrics.json").exists():
        raise SystemExit("results/v3/test_metrics.json exists: test set already used once.")
    with open(RES / "selection.json") as f:
        sel = json.load(f)
    w = sel["winner"]
    trial_id, family, fs, wm = w["trial_id"], w["family"], w["feature_set"], w["weight_mode"]

    t0 = time.perf_counter()
    if family == "stack_lr":
        families = sel["winner_params"].get("bases") or ["xgb", "lgbm"]
        proba, bundle, X = _refit_stack(data, families, wm)
    elif family == "softvote":
        base_ids = sel["winner_params"].get("bases") or ["xgb_v3_full", "lgbm_v3_full"]
        proba, bundle, X = _refit_softvote(data, base_ids, wm)
    else:
        extra = sel["winner_extra"]
        n_est = int(extra["n_estimators_used"])
        model, fit_extra, X = _refit_single(data, family, fs, wm, n_est)
        proba = predict_proba(model, X[data.te])
        bundle = {"model": model, "extra": fit_extra, "feature_set": fs,
                  "family": family, "weight_mode": wm}
    fit_s = round(time.perf_counter() - t0, 1)

    pred = proba.argmax(axis=1)
    y_te = data.y[data.te]
    cols = list(X.columns)

    joblib.dump(bundle, ART / "final_model.joblib")
    joblib.dump(data.enc, ART / "label_encoder.joblib")
    with open(ART / "feature_names.json", "w") as f:
        json.dump(cols, f)
    with open(ART / "selected_config.json", "w") as f:
        json.dump({"trial_id": trial_id, "family": family, "feature_set": fs,
                   "weight_mode": wm, "accepted": True, "refit_on": "train+val"},
                  f, indent=2)
    model_mb = round((ART / "final_model.joblib").stat().st_size / 2**20, 1)

    m = evaluate(y_te, pred)
    test_metrics = {
        "trial_id": trial_id, "family": family,
        **{k: v for k, v in m.items() if k != "confusion_matrix"},
    }
    with open(RES / "test_metrics.json", "w") as f:
        json.dump(test_metrics, f, indent=2)
    with open(RES / "classification_report.txt", "w") as f:
        f.write(classification_report(y_te, pred, target_names=CLASSES, digits=4))
    pd.DataFrame(classification_report(
        y_te, pred, target_names=CLASSES, digits=4, output_dict=True)
    ).T.round(4).to_csv(RES / "classification_report.csv")
    cm = confusion_matrix(y_te, pred, labels=range(N_CLASSES))
    pd.DataFrame(cm, index=CLASSES, columns=CLASSES).to_csv(RES / "confusion_matrix.csv")
    pd.DataFrame(cm / cm.sum(axis=1, keepdims=True), index=CLASSES, columns=CLASSES).round(4).to_csv(
        RES / "confusion_matrix_normalized.csv")

    preds = pd.DataFrame(proba, columns=[f"proba_{c}" for c in CLASSES])
    preds.insert(0, "row_id", data.df.index[data.te])
    preds.insert(1, "true", data.enc.inverse_transform(y_te))
    preds.insert(2, "pred", data.enc.inverse_transform(pred))
    preds.to_csv(RES / "test_predictions.csv", index=False)

    seen = pd.Series(data.hosts[data.te]).isin(set(data.hosts[data.trva])).to_numpy()
    labels_te = data.df.loc[data.te, "label"].to_numpy()
    subgroups = []
    for name, mask in (("all_test", np.ones_like(seen, dtype=bool)),
                       ("seen_hostname", seen), ("unseen_hostname", ~seen)):
        counts = pd.Series(labels_te[mask]).value_counts()
        sm = evaluate(y_te[mask], pred[mask])
        subgroups.append({
            "subgroup": name, "n": int(mask.sum()),
            **{f"n_{c}": int(counts.get(c, 0)) for c in CLASSES},
            **{k: sm[k] for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1")},
            **{f"recall_{c}": sm[f"recall_{c}"] for c in CLASSES},
        })
    subgroups = pd.DataFrame(subgroups)
    subgroups.to_csv(RES / "hostname_subgroup_test.csv", index=False)

    v2 = json.load(open(RES_V2 / "test_metrics.json"))
    comp_rows = []
    for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1",
              *[f"recall_{c}" for c in CLASSES],
              *[f"precision_{c}" for c in CLASSES],
              *[f"f1_{c}" for c in CLASSES]):
        comp_rows.append((k, v2[k], test_metrics[k], round(test_metrics[k] - v2[k], 4)))
    comp = pd.DataFrame(comp_rows, columns=["metric", "v2", "v3", "delta"])
    comp.to_csv(RES / "v2_vs_v3.csv", index=False)

    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        **environment(), "seed": SEED,
        "feature_set": fs, "n_features": len(cols),
        "feature_hash": hashlib.sha256(json.dumps(cols).encode()).hexdigest(),
        "selected": {"trial_id": trial_id, "family": family},
        "final_fit_seconds": fit_s, "model_size_mb": model_mb,
        "peak_memory_mb": peak_memory_mb(),
        "test_metrics": test_metrics,
    }
    with open(RES / "run_metadata.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)

    print("Test:", json.dumps(test_metrics, indent=2))
    print(subgroups[["subgroup", "n", "accuracy", "macro_f1"]].to_string(index=False))
    print(comp.to_string(index=False))


def stage_verify(data):
    bundle = joblib.load(ART / "final_model.joblib")
    enc = joblib.load(ART / "label_encoder.joblib")
    cols = json.load(open(ART / "feature_names.json"))
    assert list(enc.classes_) == CLASSES
    saved = pd.read_csv(RES / "test_predictions.csv", nrows=2000)
    row_ids = saved["row_id"].astype(int).to_numpy()
    X = data.x_full.loc[row_ids, cols]
    # Rebuild probabilities depending on bundle type.
    if "meta" in bundle and "bases" in bundle:
        blocks = [predict_proba(bundle["bases"][f], X) for f in bundle["families"]]
        proba = bundle["meta"].predict_proba(np.hstack(blocks))
    elif "bases" in bundle and bundle.get("method") == "mean_proba":
        blocks = [predict_proba(bundle["bases"][f], X) for f in ("xgb", "lgbm", "cat")]
        proba = np.mean(blocks, axis=0)
    else:
        proba = predict_proba(bundle["model"], X)
    assert np.isfinite(proba).all() and np.allclose(proba.sum(axis=1), 1, atol=1e-5)
    assert np.allclose(saved[[f"proba_{c}" for c in CLASSES]].to_numpy(), proba, atol=1e-5)
    print("Verified: final model reloads and matches saved test probabilities.")


STAGES = {
    "ablatesingle": stage_ablatesingle,
    "ensemble": stage_ensemble,
    "stack": stage_stack,
    "select": stage_select,
    "final": stage_final,
    "verify": stage_verify,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stages", nargs="+", choices=list(STAGES))
    args = parser.parse_args(argv)
    RES.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    data = Data()
    for name in args.stages:
        print(f"=== stage: {name} ===", flush=True)
        t0 = time.perf_counter()
        STAGES[name](data)
        print(f"=== {name} done in {time.perf_counter() - t0:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
