"""Stage 2: compare LR / RF / XGBoost on validation, refit the best on train+val, test once.

Also runs the raw-URL ablation: same model type, same rows, features from the un-normalized URL.
"""
import json
import platform
import time
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             precision_recall_fscore_support)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from src.data import CLASSES, SEED
from src.features import FEATURE_NAMES, RAW_EXTRA_FEATURES, hostname

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
RES = ROOT / "results"


def make_model(name):
    if name == "logreg":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=2000, random_state=SEED))
    if name == "random_forest":
        return RandomForestClassifier(
            n_estimators=200, max_depth=25, min_samples_leaf=5,
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEED)
    if name == "xgboost":
        return XGBClassifier(
            n_estimators=500, max_depth=8, learning_rate=0.1, subsample=0.8,
            colsample_bytree=0.8, tree_method="hist", objective="multi:softprob",
            eval_metric="mlogloss", n_jobs=-1, random_state=SEED)
    raise ValueError(name)


def fit(name, X, y):
    model = make_model(name)
    if name == "xgboost":
        model.fit(X, y, sample_weight=compute_sample_weight("balanced", y))
    else:
        model.fit(X, y)
    return model


def metrics(y_true, y_pred):
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
    per_class_recall = precision_recall_fscore_support(
        y_true, y_pred, labels=range(len(CLASSES)), zero_division=0)[1]
    out = {"accuracy": accuracy_score(y_true, y_pred), "macro_precision": p,
           "macro_recall": r, "macro_f1": f1}
    out.update({f"recall_{c}": v for c, v in zip(CLASSES, per_class_recall)})
    return {k: round(float(v), 4) for k, v in out.items()}


def main():
    df = pd.read_parquet(ART / "clean.parquet")
    X_norm = pd.read_parquet(ART / "features_norm.parquet")
    X_raw = pd.read_parquet(ART / "features_raw.parquet")

    enc = LabelEncoder().fit(CLASSES)
    y = enc.transform(df["label"])
    tr = (df["split"] == "train").to_numpy()
    va = (df["split"] == "val").to_numpy()
    te = (df["split"] == "test").to_numpy()
    trva = tr | va
    assert not (tr & va).any() and not (tr & te).any() and not (va & te).any()

    # Model comparison on validation (test untouched)
    rows = []
    for name in ("logreg", "random_forest", "xgboost"):
        t0 = time.perf_counter()
        model = fit(name, X_norm[tr], y[tr])
        fit_s = time.perf_counter() - t0
        m = metrics(y[va], model.predict(X_norm[va]))
        rows.append({"model": name, **m, "fit_seconds": round(fit_s, 1)})
        print(rows[-1])
    comparison = pd.DataFrame(rows)
    comparison.to_csv(RES / "model_comparison_val.csv", index=False)
    best = comparison.sort_values("macro_f1", ascending=False).iloc[0]["model"]
    print(f"Selected by validation macro-F1: {best}")

    # Final model: refit on train+val, evaluate once on test
    model = fit(best, X_norm[trva], y[trva])
    proba = model.predict_proba(X_norm[te])
    pred = proba.argmax(axis=1)
    test_metrics = metrics(y[te], pred)
    print("Test:", test_metrics)

    joblib.dump(model, ART / "final_model.joblib")
    joblib.dump(enc, ART / "label_encoder.joblib")
    with open(ART / "feature_names.json", "w") as f:
        json.dump(list(X_norm.columns), f)

    preds = pd.DataFrame(proba, columns=[f"proba_{c}" for c in enc.classes_])
    preds.insert(0, "row_id", df.index[te])
    preds.insert(1, "true", enc.inverse_transform(y[te]))
    preds.insert(2, "pred", enc.inverse_transform(pred))
    preds.to_csv(RES / "test_predictions.csv", index=False)

    with open(RES / "test_metrics.json", "w") as f:
        json.dump({"model": best, **test_metrics}, f, indent=2)
    with open(RES / "classification_report.txt", "w") as f:
        f.write(classification_report(y[te], pred, target_names=enc.classes_, digits=4))
    cm = confusion_matrix(y[te], pred)
    pd.DataFrame(cm, index=enc.classes_, columns=enc.classes_).to_csv(RES / "confusion_matrix.csv")
    pd.DataFrame(cm / cm.sum(axis=1, keepdims=True), index=enc.classes_,
                 columns=enc.classes_).round(4).to_csv(RES / "confusion_matrix_normalized.csv")

    # Three-way ablation on identical rows and model type: separates general formatting
    # effects (raw string, same 24 features) from explicit scheme indicators (+2 flags).
    ablation = [{"input": "normalized_url (primary)", "n_features": X_norm.shape[1], **test_metrics}]
    for label, cols in [("raw_url, same features", FEATURE_NAMES),
                        ("raw_url + is_https, has_scheme", FEATURE_NAMES + RAW_EXTRA_FEATURES)]:
        m = fit(best, X_raw.loc[trva, cols], y[trva])
        ablation.append({"input": label, "n_features": len(cols),
                         **metrics(y[te], m.predict(X_raw.loc[te, cols]))})
        del m
    ablation = pd.DataFrame(ablation)
    ablation.to_csv(RES / "ablation_raw_vs_normalized.csv", index=False)
    print(ablation[["input", "n_features", "accuracy", "macro_f1"]])

    # Hostname-overlap subgroups: hosts seen in train+val (what the final model was fit on)
    hosts = df["url_norm"].map(hostname)
    seen = hosts[te].isin(set(hosts[trva])).to_numpy()
    subgroups = []
    for name, mask in [("all_test", np.ones_like(seen)), ("seen_hostname", seen), ("unseen_hostname", ~seen)]:
        counts = df.loc[te, "label"][mask].value_counts()
        subgroups.append({"subgroup": name, "n": int(mask.sum()),
                          **{f"n_{c}": int(counts.get(c, 0)) for c in CLASSES},
                          **metrics(y[te][mask], pred[mask])})
    subgroups = pd.DataFrame(subgroups)
    subgroups.to_csv(RES / "hostname_subgroup_test.csv", index=False)
    print(subgroups[["subgroup", "n", "accuracy", "macro_f1"]])

    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(), "platform": platform.platform(),
        "processor": platform.processor(), "seed": SEED, "dataset": "malicious_phish.csv",
        "sklearn": sklearn.__version__, "xgboost": xgboost.__version__,
        "selected_model": best, "model_params": make_model(best).get_params(deep=False),
    }
    with open(RES / "run_metadata.json", "w") as f:
        json.dump(meta, f, indent=2, default=str)


if __name__ == "__main__":
    main()
