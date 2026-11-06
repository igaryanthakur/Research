"""V2 stage 2: baseline reproduction, feature ablation, bounded validation-only tuning,
winner selection, one-time test evaluation and artifact verification.

Usage: python train_v2.py STAGE [STAGE ...]
Stages (in order): baseline ablation lr rf xgb select final verify
Trials are appended to results/v2/model_trials_val.csv and skipped when already recorded.
"""
import argparse
import gc
import hashlib
import json
import math
import time
import traceback
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             precision_recall_fscore_support)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

from src.data import CLASSES, SEED
from src.features import FEATURE_NAMES, hostname
from src.features_v2 import FEATURE_NAMES_V2, LEXICON_FEATURES, STRUCTURAL_FEATURES
from src.runinfo import environment, peak_memory_mb

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts" / "v2"
RES = ROOT / "results" / "v2"
V1_RES = ROOT / "results"
TRIALS = RES / "model_trials_val.csv"

MALICIOUS = ["defacement", "malware", "phishing"]
V1_VAL = {"accuracy": 0.8463, "macro_f1": 0.8254, "recall_defacement": 0.8859,
          "recall_malware": 0.8808, "recall_phishing": 0.7933}
V1_MODEL_MB = 565.0
TIE_F1 = 0.005
MIN_MALICIOUS_RECALL = 0.70
MAX_RECALL_DROP = 0.05
COMPENSATING_F1 = V1_VAL["macro_f1"] + 0.01
BASELINE_TOLERANCE = 0.001

RF_BUDGET_GB = 3.0
RF_CHUNK = 50
RF_BYTES_PER_NODE = 64 + 8 * len(CLASSES)
V1_RF = {"n_estimators": 200, "max_depth": 25, "min_samples_leaf": 5, "max_features": "sqrt"}

TUNING_STAGES = ["lr", "rf_coarse", "rf_refine", "rf_control", "xgb"]
METRIC_COLS = (
    ["accuracy", "macro_precision", "macro_recall", "macro_f1",
     "weighted_precision", "weighted_recall", "weighted_f1"]
    + [f"{m}_{c}" for c in CLASSES for m in ("precision", "recall", "f1", "support")]
    + ["unseen_host_n", "unseen_host_accuracy", "unseen_host_macro_f1", "confusion_matrix"])
COLUMNS = (["trial_id", "stage", "family", "feature_set", "n_features", "weight_mode",
            "class_weights", "params", "extra", "status", "error", "fit_s", "predict_s",
            "peak_memory_mb", "timestamp"] + METRIC_COLS)


class BudgetExceeded(Exception):
    pass


# ---------------------------------------------------------------- data

class Data:
    def __init__(self):
        self.df = pd.read_parquet(ART / "clean.parquet")
        self.x1 = pd.read_parquet(ART / "features_v1_norm.parquet")
        self.x2 = pd.read_parquet(ART / "features_v2_norm.parquet")
        with open(ART / "feature_manifest.json") as f:
            self.manifest = json.load(f)
        assert self.x1.index.equals(self.df.index) and self.x2.index.equals(self.df.index)
        assert list(self.x1.columns) == FEATURE_NAMES and list(self.x2.columns) == FEATURE_NAMES_V2

        self.enc = LabelEncoder().fit(CLASSES)
        assert list(self.enc.classes_) == CLASSES
        self.y = self.enc.transform(self.df["label"])
        split = self.df["split"].to_numpy()
        self.tr, self.va, self.te = split == "train", split == "val", split == "test"
        self.trva = self.tr | self.va
        assert not (self.tr & self.va).any() and not (self.trva & self.te).any()

        self.hosts = self.df["url_norm"].map(hostname).to_numpy()
        train_hosts = set(self.hosts[self.tr])
        self.va_unseen = ~pd.Series(self.hosts[self.va]).isin(train_hosts).to_numpy()

    def features(self, feature_set):
        return self.x1 if feature_set == "v1" else self.x2[feature_columns(feature_set, self.manifest)]


def feature_columns(feature_set, manifest=None):
    dropped = set((manifest or {}).get("dropped_features", {}))
    cols = {"v1": FEATURE_NAMES,
            "v1_structural": FEATURE_NAMES + STRUCTURAL_FEATURES,
            "v1_lexicon": FEATURE_NAMES + LEXICON_FEATURES,
            "v2_full": FEATURE_NAMES_V2}[feature_set]
    return [c for c in cols if c not in dropped]


# ---------------------------------------------------------------- weights, metrics, rules

def class_weights(y, mode):
    """None, or {class_index: weight} from the label counts of the fitting set."""
    if mode == "none":
        return None
    counts = np.bincount(y, minlength=len(CLASSES))
    base = len(y) / (len(CLASSES) * counts)
    power = {"sqrt_balanced": 0.5, "balanced": 1.0}[mode]
    return {int(k): float(w ** power) for k, w in enumerate(base)}


def evaluate(y_true, y_pred, unseen=None):
    labels = list(range(len(CLASSES)))
    out = {"accuracy": accuracy_score(y_true, y_pred)}
    for avg in ("macro", "weighted"):
        p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average=avg, zero_division=0)
        out.update({f"{avg}_precision": p, f"{avg}_recall": r, f"{avg}_f1": f})
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    for i, c in enumerate(CLASSES):
        out.update({f"precision_{c}": p[i], f"recall_{c}": r[i], f"f1_{c}": f[i], f"support_{c}": s[i]})
    out = {k: round(float(v), 4) if not k.startswith("support") else int(v) for k, v in out.items()}
    if unseen is not None:
        out["unseen_host_n"] = int(unseen.sum())
        out["unseen_host_accuracy"] = round(float(accuracy_score(y_true[unseen], y_pred[unseen])), 4)
        out["unseen_host_macro_f1"] = round(float(precision_recall_fscore_support(
            y_true[unseen], y_pred[unseen], average="macro", zero_division=0)[2]), 4)
    out["confusion_matrix"] = json.dumps(confusion_matrix(y_true, y_pred, labels=labels).tolist())
    return out


def order_by_rule(df):
    """Order rows by repeatedly applying the fixed rule: max macro-F1; among rows within
    TIE_F1 of it, higher accuracy, then higher minimum malicious recall, then lower fit time."""
    df = df.assign(min_malicious_recall=df[[f"recall_{c}" for c in MALICIOUS]].min(axis=1))
    remaining = df.copy()
    ordered = []
    while len(remaining):
        near = remaining[remaining["macro_f1"] >= remaining["macro_f1"].max() - TIE_F1]
        pick = near.sort_values(["accuracy", "min_malicious_recall", "fit_s"],
                                ascending=[False, False, True]).index[0]
        ordered.append(pick)
        remaining = remaining.drop(index=pick)
    return df.loc[ordered]


def eligibility(row):
    reasons = []
    if not row["accuracy"] > V1_VAL["accuracy"]:
        reasons.append(f"accuracy {row['accuracy']} <= V1 {V1_VAL['accuracy']}")
    if not row["macro_f1"] >= V1_VAL["macro_f1"]:
        reasons.append(f"macro_f1 {row['macro_f1']} < V1 {V1_VAL['macro_f1']}")
    for c in MALICIOUS:
        r = row[f"recall_{c}"]
        if r < MIN_MALICIOUS_RECALL:
            reasons.append(f"recall_{c} {r} < {MIN_MALICIOUS_RECALL}")
        if V1_VAL[f"recall_{c}"] - r > MAX_RECALL_DROP and row["macro_f1"] < COMPENSATING_F1:
            reasons.append(f"recall_{c} {r} dropped > {MAX_RECALL_DROP} vs V1 without macro_f1 >= {COMPENSATING_F1:.4f}")
    return not reasons, reasons


# ---------------------------------------------------------------- model fitting

def schema_hash(columns):
    """sha256 of the ordered column list, matching prepare_v2's manifest hash format."""
    return hashlib.sha256(json.dumps(list(columns)).encode()).hexdigest()


def rf_size_mb(model):
    return sum(t.tree_.node_count for t in model.estimators_) * RF_BYTES_PER_NODE / 2**20


def fit_rf(X, y, params, cw, on_budget="abort"):
    """Grow the forest in warm-start chunks (identical to a single fit for a fixed seed) and
    stop when the projected tree memory exceeds RF_BUDGET_GB: abort, or cap the tree count."""
    params = dict(params)
    target = params.pop("n_estimators")
    budget_mb = RF_BUDGET_GB * 1024
    if isinstance(cw, str):
        model = RandomForestClassifier(n_estimators=target, class_weight=cw, bootstrap=True,
                                       n_jobs=-1, random_state=SEED, **params).fit(X, y)
        return model, {"n_estimators_used": target, "est_size_mb": round(rf_size_mb(model), 1)}

    model = RandomForestClassifier(n_estimators=0, class_weight=cw, bootstrap=True, warm_start=True,
                                   n_jobs=-1, random_state=SEED, **params)
    capped = False
    while model.n_estimators < target:
        model.n_estimators = min(model.n_estimators + RF_CHUNK, target)
        model.fit(X, y)
        per_tree = rf_size_mb(model) / len(model.estimators_)
        if per_tree * target > budget_mb:
            if on_budget == "abort":
                raise BudgetExceeded(f"projected {per_tree * target:.0f} MB for {target} trees "
                                     f"> budget {budget_mb:.0f} MB")
            allowed = max(int(budget_mb / per_tree) // RF_CHUNK * RF_CHUNK, len(model.estimators_))
            if allowed < target:
                target, capped = allowed, True
    model.warm_start = False
    return model, {"n_estimators_used": len(model.estimators_), "capped_by_budget": capped,
                   "est_size_mb": round(rf_size_mb(model), 1)}


def fit_lr(X, y, params, cw):
    max_iter = params.get("max_iter", 2000)
    for attempt in range(2):
        model = make_pipeline(StandardScaler(), LogisticRegression(
            C=params["C"], class_weight=cw, max_iter=max_iter, random_state=SEED))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(X, y)
        converged = not any(issubclass(w.category, ConvergenceWarning) for w in caught)
        if converged or attempt == 1:
            break
        max_iter = 5000
    return model, {"max_iter_used": max_iter, "converged": converged,
                   "n_iter": int(np.max(model[-1].n_iter_))}


def xgb_model(params, n_estimators, early_stopping=None):
    return XGBClassifier(n_estimators=n_estimators, early_stopping_rounds=early_stopping,
                         objective="multi:softprob", eval_metric="mlogloss", tree_method="hist",
                         n_jobs=-1, random_state=SEED, **params)


def row_weights(y, cw):
    return None if cw is None else np.array([cw[int(k)] for k in y])


def fit_xgb(X, y, params, cw, X_val=None, y_val=None, n_estimators=None):
    if n_estimators is None:
        model = xgb_model(params, 1000, early_stopping=50)
        model.fit(X, y, sample_weight=row_weights(y, cw), eval_set=[(X_val, y_val)], verbose=False)
        return model, {"best_iteration": int(model.best_iteration),
                       "best_val_mlogloss": round(float(model.best_score), 5),
                       "n_estimators_used": int(model.best_iteration) + 1}
    model = xgb_model(params, n_estimators)
    model.fit(X, y, sample_weight=row_weights(y, cw), verbose=False)
    return model, {"n_estimators_used": n_estimators}


def fit_family(data, family, params, weight_mode, X, y, final_trees=None, on_budget="abort"):
    cw = weight_mode if weight_mode == "balanced_subsample" else class_weights(y, weight_mode)
    if family == "lr":
        model, extra = fit_lr(X, y, params, cw)
    elif family == "rf":
        if final_trees is not None:
            params = {**params, "n_estimators": final_trees}
        model, extra = fit_rf(X, y, params, cw, on_budget)
    elif family == "xgb":
        if final_trees is None:
            model, extra = fit_xgb(X, y, params, cw, data.features_val, y_val=data.y[data.va])
        else:
            model, extra = fit_xgb(X, y, params, cw, n_estimators=final_trees)
    else:
        raise ValueError(family)
    return model, extra, cw


# ---------------------------------------------------------------- trial bookkeeping

def load_trials():
    return pd.read_csv(TRIALS) if TRIALS.exists() else pd.DataFrame(columns=COLUMNS)


def append_trial(row):
    frame = pd.DataFrame([row]).reindex(columns=COLUMNS)
    frame.to_csv(TRIALS, mode="a", header=not TRIALS.exists(), index=False)


def run_trial(data, trial_id, stage, family, feature_set, params, weight_mode, on_budget="abort"):
    done = load_trials()
    prior = done[(done["trial_id"] == trial_id) & done["status"].isin(["ok", "skipped_memory_budget"])]
    if len(prior):
        print(f"[skip] {trial_id} already recorded ({prior.iloc[-1]['status']})")
        return prior.iloc[-1].to_dict()

    X = data.features(feature_set)
    data.features_val = X[data.va]
    row = {"trial_id": trial_id, "stage": stage, "family": family, "feature_set": feature_set,
           "n_features": X.shape[1], "weight_mode": weight_mode, "params": json.dumps(params),
           "timestamp": datetime.now().isoformat(timespec="seconds")}
    model = None
    t0 = time.perf_counter()
    try:
        model, extra, cw = fit_family(data, family, params, weight_mode, X[data.tr], data.y[data.tr],
                                      on_budget=on_budget)
        row["fit_s"] = round(time.perf_counter() - t0, 1)
        t1 = time.perf_counter()
        pred = model.predict(X[data.va])
        row["predict_s"] = round(time.perf_counter() - t1, 1)
        row.update(evaluate(data.y[data.va], np.asarray(pred).astype(int), data.va_unseen))
        row.update({"status": "ok", "extra": json.dumps(extra),
                    "class_weights": json.dumps(cw)})
    except BudgetExceeded as exc:
        row.update({"status": "skipped_memory_budget", "error": str(exc),
                    "fit_s": round(time.perf_counter() - t0, 1)})
    except Exception as exc:
        row.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                    "fit_s": round(time.perf_counter() - t0, 1)})
        traceback.print_exc()
    row["peak_memory_mb"] = peak_memory_mb()
    append_trial(row)
    del model
    data.features_val = None
    gc.collect()
    shown = {k: row.get(k) for k in ("trial_id", "status", "accuracy", "macro_f1", "recall_phishing",
                                     "unseen_host_macro_f1", "fit_s")}
    print(shown, flush=True)
    return row


def ok_trials(stages):
    df = load_trials()
    df = df[df["stage"].isin(stages) & (df["status"] == "ok")]
    return df.drop_duplicates("trial_id", keep="last")


# ---------------------------------------------------------------- stages

def stage_baseline(data):
    row = run_trial(data, "baseline_v1_rf", "baseline", "rf", "v1", V1_RF, "balanced_subsample")
    diffs = {k: abs(float(row[k]) - V1_VAL[k]) for k in ("accuracy", "macro_f1")}
    print("Baseline vs V1 validation:", diffs)
    if max(diffs.values()) > BASELINE_TOLERANCE:
        raise SystemExit(f"Baseline differs from V1 by more than {BASELINE_TOLERANCE}: {diffs}")


def stage_ablation(data):
    for fs in ("v1_structural", "v1_lexicon", "v2_full"):
        run_trial(data, f"ablation_rf_{fs}", "ablation", "rf", fs, V1_RF, "balanced_subsample")
    rows = ok_trials(["baseline", "ablation"])
    cols = ["trial_id", "feature_set", "n_features", "accuracy", "macro_precision", "macro_recall",
            "macro_f1", *[f"recall_{c}" for c in CLASSES], "unseen_host_accuracy",
            "unseen_host_macro_f1", "fit_s", "predict_s"]
    ordered = order_by_rule(rows)
    ordered[cols].to_csv(RES / "feature_ablation_val.csv", index=False)
    locked = ordered.iloc[0]
    lock = {"feature_set": locked["feature_set"],
            "features": feature_columns(locked["feature_set"], data.manifest),
            "rule": "order_by_rule on validation (macro-F1, 0.005 tie -> accuracy)",
            "candidates": ordered[["feature_set", "accuracy", "macro_f1"]].to_dict("records"),
            "locked_at": datetime.now().isoformat(timespec="seconds")}
    with open(RES / "feature_set_lock.json", "w") as f:
        json.dump(lock, f, indent=2)
    print(ordered[cols[:7]].to_string(index=False))
    print("Locked feature set:", lock["feature_set"])


def locked_feature_set():
    path = RES / "feature_set_lock.json"
    if not path.exists():
        raise SystemExit("Run the ablation stage first to lock the feature set.")
    with open(path) as f:
        return json.load(f)["feature_set"]


def stage_lr(data):
    fs = locked_feature_set()
    for C in (0.1, 1.0, 10.0):
        for wm in ("none", "sqrt_balanced", "balanced"):
            run_trial(data, f"lr_C{C}_{wm}", "lr", "lr", fs, {"C": C, "max_iter": 2000}, wm)


def stage_rf(data):
    fs = locked_feature_set()
    for depth in (25, None):
        for leaf in (1, 3, 5):
            for wm in ("none", "sqrt_balanced"):
                params = {"n_estimators": 300, "max_depth": depth, "min_samples_leaf": leaf,
                          "max_features": "sqrt"}
                run_trial(data, f"rf_coarse_d{depth}_l{leaf}_{wm}", "rf_coarse", "rf", fs, params, wm)

    coarse = ok_trials(["rf_coarse"])
    eligible = coarse[[eligibility(r)[0] for _, r in coarse.iterrows()]]
    for _, best in order_by_rule(eligible if len(eligible) else coarse).head(2).iterrows():
        base = json.loads(best["params"])
        for mf in ("sqrt", 0.5):
            params = {**base, "n_estimators": 500, "max_features": mf}
            tid = f"rf_refine_d{base['max_depth']}_l{base['min_samples_leaf']}_{best['weight_mode']}_mf{mf}"
            run_trial(data, tid, "rf_refine", "rf", fs, params, best["weight_mode"], on_budget="cap")
    run_trial(data, "rf_control_v1cfg", "rf_control", "rf", fs, V1_RF, "balanced_subsample")


def stage_xgb(data):
    fs = locked_feature_set()
    for depth in (6, 8, 10):
        for lr in (0.05, 0.1):
            for wm in ("none", "sqrt_balanced"):
                params = {"max_depth": depth, "learning_rate": lr, "subsample": 0.8,
                          "colsample_bytree": 0.8}
                run_trial(data, f"xgb_d{depth}_lr{lr}_{wm}", "xgb", "xgb", fs, params, wm)


def stage_select(data):
    trials = ok_trials(TUNING_STAGES)
    elig = trials.apply(eligibility, axis=1, result_type="expand")
    trials["eligible"], trials["ineligible_reasons"] = elig[0], elig[1].map("; ".join)
    trials = order_by_rule(trials)

    cols = ["family", "trial_id", "weight_mode", "params", "n_features", "accuracy",
            "macro_precision", "macro_recall", "macro_f1", *[f"recall_{c}" for c in CLASSES],
            "unseen_host_accuracy", "unseen_host_macro_f1", "fit_s", "predict_s", "eligible",
            "ineligible_reasons"]
    best_per_family = pd.concat([
        order_by_rule(g[g["eligible"]] if g["eligible"].any() else g).head(1)
        for _, g in trials.groupby("family")])
    order_by_rule(best_per_family)[cols].to_csv(RES / "model_comparison_val.csv", index=False)
    trials[cols].to_csv(RES / "model_trials_ranked_val.csv", index=False)

    eligible = trials[trials["eligible"]]
    accepted = len(eligible) > 0
    pool = order_by_rule(eligible) if accepted else trials
    winner = pool.iloc[0]
    near = pool[pool["macro_f1"] >= pool["macro_f1"].max() - TIE_F1]
    selection = {
        "accepted_over_v1": bool(accepted),
        "decision": ("V2 winner replaces V1" if accepted else
                     "No V2 configuration passed the gate: V1 retained; V2 winner is experimental only"),
        "winner": {k: winner[k] for k in ("trial_id", "family", "feature_set", "weight_mode")},
        "winner_params": json.loads(winner["params"]),
        "winner_extra": json.loads(winner["extra"]),
        "winner_val_metrics": {k: winner[k] for k in METRIC_COLS if k != "confusion_matrix"},
        "rule": ("eligible = acc > V1 0.8463, macro_f1 >= 0.8254, malicious recall >= 0.70, no malicious "
                 "recall drop > 0.05 vs V1 unless macro_f1 >= 0.8354; then max macro-F1, within 0.005 "
                 "higher accuracy, then higher min malicious recall, then lower fit time"),
        "v1_val_reference": V1_VAL,
        "near_tie_candidates": near[["trial_id", "accuracy", "macro_f1", "min_malicious_recall",
                                     "fit_s"]].to_dict("records"),
        "n_trials": int(len(trials)), "n_eligible": int(len(eligible)),
        "best_per_family": best_per_family[["family", "trial_id", "accuracy", "macro_f1",
                                            "eligible"]].to_dict("records"),
        "selected_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(RES / "selection.json", "w") as f:
        json.dump(selection, f, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(order_by_rule(best_per_family)[cols[:9] + ["eligible"]].to_string(index=False))
    print(selection["decision"], "->", selection["winner"])


def stage_final(data):
    if (RES / "test_metrics.json").exists():
        raise SystemExit("results/v2/test_metrics.json exists: the test set has already been used once.")
    with open(RES / "selection.json") as f:
        sel = json.load(f)
    w = sel["winner"]
    family, fs, wm = w["family"], w["feature_set"], w["weight_mode"]
    params = sel["winner_params"]
    trees = sel["winner_extra"].get("n_estimators_used")
    X = data.features(fs)
    cols = list(X.columns)

    t0 = time.perf_counter()
    model, extra, cw = fit_family(data, family, params, wm, X[data.trva], data.y[data.trva],
                                  final_trees=trees, on_budget="cap")
    fit_s = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    proba = model.predict_proba(X[data.te])
    predict_s = round(time.perf_counter() - t0, 1)
    pred = proba.argmax(axis=1)
    y_te = data.y[data.te]

    ART.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, ART / "final_model.joblib")
    joblib.dump(data.enc, ART / "label_encoder.joblib")
    with open(ART / "feature_names.json", "w") as f:
        json.dump(cols, f)
    selected = {"trial_id": w["trial_id"], "family": family, "feature_set": fs, "weight_mode": wm,
                "params": params, "final_fit_extra": extra, "class_weights_final": cw,
                "accepted_over_v1": sel["accepted_over_v1"], "refit_on": "train+val"}
    with open(ART / "selected_config.json", "w") as f:
        json.dump(selected, f, indent=2, default=str)
    model_mb = round((ART / "final_model.joblib").stat().st_size / 2**20, 1)

    m = evaluate(y_te, pred)
    test_metrics = {"trial_id": w["trial_id"], "family": family, "accepted_over_v1": sel["accepted_over_v1"],
                    **{k: v for k, v in m.items() if k != "confusion_matrix"}}
    with open(RES / "test_metrics.json", "w") as f:
        json.dump(test_metrics, f, indent=2)
    with open(RES / "classification_report.txt", "w") as f:
        f.write(classification_report(y_te, pred, target_names=CLASSES, digits=4))
    pd.DataFrame(classification_report(y_te, pred, target_names=CLASSES, digits=4, output_dict=True)
                 ).T.round(4).to_csv(RES / "classification_report.csv")
    cm = confusion_matrix(y_te, pred, labels=range(len(CLASSES)))
    pd.DataFrame(cm, index=CLASSES, columns=CLASSES).to_csv(RES / "confusion_matrix.csv")
    pd.DataFrame(cm / cm.sum(axis=1, keepdims=True), index=CLASSES,
                 columns=CLASSES).round(4).to_csv(RES / "confusion_matrix_normalized.csv")

    preds = pd.DataFrame(proba, columns=[f"proba_{c}" for c in CLASSES])
    preds.insert(0, "row_id", data.df.index[data.te])
    preds.insert(1, "true", data.enc.inverse_transform(y_te))
    preds.insert(2, "pred", data.enc.inverse_transform(pred))
    preds.to_csv(RES / "test_predictions.csv", index=False)

    seen = pd.Series(data.hosts[data.te]).isin(set(data.hosts[data.trva])).to_numpy()
    labels_te = data.df.loc[data.te, "label"].to_numpy()
    subgroups = []
    for name, mask in [("all_test", np.ones_like(seen)), ("seen_hostname", seen), ("unseen_hostname", ~seen)]:
        counts = pd.Series(labels_te[mask]).value_counts()
        sm = evaluate(y_te[mask], pred[mask])
        subgroups.append({"subgroup": name, "n": int(mask.sum()),
                          **{f"n_{c}": int(counts.get(c, 0)) for c in CLASSES},
                          **{k: sm[k] for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1")},
                          **{f"recall_{c}": sm[f"recall_{c}"] for c in CLASSES}})
    subgroups = pd.DataFrame(subgroups)
    subgroups.to_csv(RES / "hostname_subgroup_test.csv", index=False)

    v1_test = json.load(open(V1_RES / "test_metrics.json"))
    v1_sub = pd.read_csv(V1_RES / "hostname_subgroup_test.csv").set_index("subgroup")
    v1_val = pd.read_csv(V1_RES / "model_comparison_val.csv").set_index("model").loc["random_forest"]
    v2_sub = subgroups.set_index("subgroup")
    v2_val = sel["winner_val_metrics"]
    trial_fit = float(ok_trials(TUNING_STAGES).set_index("trial_id").loc[w["trial_id"], "fit_s"])
    comp = [("val_accuracy", v1_val["accuracy"], v2_val["accuracy"]),
            ("val_macro_f1", v1_val["macro_f1"], v2_val["macro_f1"])]
    for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1", *[f"recall_{c}" for c in CLASSES]):
        comp.append((f"test_{k}", v1_test[k], test_metrics[k]))
    for g in ("seen_hostname", "unseen_hostname"):
        for k in ("accuracy", "macro_f1"):
            comp.append((f"test_{g}_{k}", v1_sub.loc[g, k], v2_sub.loc[g, k]))
    comp += [("fit_seconds_train_only", v1_val["fit_seconds"], trial_fit),
             ("model_size_mb", V1_MODEL_MB, model_mb)]
    comp = pd.DataFrame(comp, columns=["metric", "v1", "v2"])
    comp["delta"] = (comp["v2"] - comp["v1"]).round(4)
    comp.to_csv(RES / "v1_vs_v2.csv", index=False)

    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"), **environment(), "seed": SEED,
        "dataset": "malicious_phish.csv",
        "dataset_sha256": json.load(open(RES / "data_audit.json")).get("dataset_sha256"),
        "row_counts": {"train": int(data.tr.sum()), "val": int(data.va.sum()), "test": int(data.te.sum())},
        "feature_set": fs, "features": cols, "n_features": len(cols),
        "feature_hash": schema_hash(cols),
        "generated_feature_hash": data.manifest.get("feature_hash"),
        "selected": selected, "final_fit_seconds": fit_s, "test_predict_seconds": predict_s,
        "model_size_mb": model_mb, "peak_memory_mb": peak_memory_mb(),
    }
    with open(RES / "run_metadata.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)
    print("Test:", json.dumps(test_metrics, indent=2))
    print(subgroups[["subgroup", "n", "accuracy", "macro_f1"]].to_string(index=False))
    print(comp.to_string(index=False))


def stage_verify(data):
    model = joblib.load(ART / "final_model.joblib")
    enc = joblib.load(ART / "label_encoder.joblib")
    cols = json.load(open(ART / "feature_names.json"))
    assert list(enc.classes_) == CLASSES
    assert list(model.classes_) == list(range(len(CLASSES)))
    X = data.x2[cols] if set(cols) <= set(FEATURE_NAMES_V2) else data.x1[cols]
    sample = X[data.te].iloc[:5000]
    proba = model.predict_proba(sample)
    assert np.isfinite(proba).all() and np.allclose(proba.sum(axis=1), 1, atol=1e-5)
    saved = pd.read_csv(RES / "test_predictions.csv", nrows=5000)
    assert (saved["row_id"].to_numpy() == sample.index.to_numpy()).all()
    assert np.allclose(saved[[f"proba_{c}" for c in CLASSES]].to_numpy(), proba, atol=1e-5)
    assert (enc.inverse_transform(proba.argmax(axis=1)) == saved["pred"].to_numpy()).all()
    print("Verified: artifacts reload; probabilities finite, sum to 1, and match saved predictions.")


STAGES = {"baseline": stage_baseline, "ablation": stage_ablation, "lr": stage_lr, "rf": stage_rf,
          "xgb": stage_xgb, "select": stage_select, "final": stage_final, "verify": stage_verify}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stages", nargs="+", choices=list(STAGES))
    args = parser.parse_args(argv)
    RES.mkdir(parents=True, exist_ok=True)
    data = Data()
    data.features_val = None
    for name in args.stages:
        print(f"=== stage: {name} ===", flush=True)
        t0 = time.perf_counter()
        STAGES[name](data)
        print(f"=== {name} done in {time.perf_counter() - t0:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
