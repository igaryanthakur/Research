"""XAI stage 1: freeze a 500-URL test sample and generate SHAP and LIME explanations with
per-instance timings for the frozen V2 classifier.

Usage: python explain_v2.py [--pilot N]
Explanations are appended per URL and skipped on rerun; never regenerate to improve findings.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost
from lime.lime_tabular import LimeTabularExplainer

from src.data import CLASSES, SEED
from src.runinfo import environment

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts" / "v2"
RES = ROOT / "results" / "v2"
OUT = RES / "xai"

PER_CLASS = 125
LIME_SAMPLES = 2000
LIME_BACKGROUND = 10_000


def check_frozen():
    with open(RES / "freeze.json") as f:
        frozen = json.load(f)["sha256"]
    for rel, digest in frozen.items():
        actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        if actual != digest:
            raise SystemExit(f"{rel} changed since the classifier was frozen.")


def load():
    model = joblib.load(ART / "final_model.joblib")
    cols = json.loads((ART / "feature_names.json").read_text())
    df = pd.read_parquet(ART / "clean.parquet")
    X = pd.read_parquet(ART / "features_v2_norm.parquet")[cols]
    preds = pd.read_csv(RES / "test_predictions.csv")
    return model, cols, df, X, preds


def freeze_sample(df, preds):
    """125 test URLs per predicted class (seed 42), saved before any explanation is computed."""
    path = OUT / "xai_sample.csv"
    if path.exists():
        return pd.read_csv(path)
    preds = preds.assign(correct=preds["true"] == preds["pred"])
    sample = (preds.groupby("pred", group_keys=False)
              .apply(lambda g: g.sample(n=min(PER_CLASS, len(g)), random_state=SEED))
              .sort_values(["pred", "row_id"]).reset_index(drop=True))
    sample.insert(1, "url_norm", df.loc[sample["row_id"], "url_norm"].to_numpy())
    sample.to_csv(path, index=False)
    return sample


def tree_shap(booster, x):
    """Exact path-dependent TreeSHAP from XGBoost's built-in implementation.

    shap 0.49.1 cannot load XGBoost 3.x multiclass models (vector base_score), so the
    contributions come from Booster.predict(pred_contribs=True): shape (n, classes, features + 1),
    last column is the bias term, values are in margin (log-odds) space.
    """
    contribs = booster.predict(xgboost.DMatrix(x), pred_contribs=True)
    assert contribs.shape == (len(x), len(CLASSES), x.shape[1] + 1), contribs.shape
    return contribs


def retime():
    """Re-measure per-URL timings only, identical protocol, explanations are not saved.

    Used because the main run showed simultaneous ~4x slowdowns of both methods in some blocks
    (external machine load); the explanation values themselves are unaffected.
    """
    check_frozen()
    model, cols, df, X, preds = load()
    sample = pd.read_csv(OUT / "xai_sample.csv")
    class_index = {c: i for i, c in enumerate(CLASSES)}
    train_rows = df.index[(df["split"] == "train").to_numpy()]
    background = X.loc[train_rows].sample(n=LIME_BACKGROUND, random_state=SEED).to_numpy()
    lime_explainer = LimeTabularExplainer(
        background, feature_names=cols, class_names=CLASSES, discretize_continuous=True,
        mode="classification", random_state=SEED)
    booster = model.get_booster()

    def predict_fn(a):
        return model.predict_proba(pd.DataFrame(a, columns=cols))

    warm = X.loc[[int(preds.loc[~preds["row_id"].isin(sample["row_id"]), "row_id"].iloc[0])]]
    tree_shap(booster, warm)
    lime_explainer.explain_instance(warm.to_numpy()[0], predict_fn, num_features=len(cols),
                                    labels=(0,), num_samples=LIME_SAMPLES)
    rows = []
    for i, row in enumerate(sample.itertuples(index=False), 1):
        cls, x = class_index[row.pred], X.loc[[row.row_id]]
        t0 = time.perf_counter()
        tree_shap(booster, x)
        shap_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        lime_explainer.explain_instance(x.to_numpy()[0], predict_fn, num_features=len(cols),
                                        labels=(cls,), num_samples=LIME_SAMPLES)
        lime_s = time.perf_counter() - t0
        rows.append({"row_id": row.row_id, "pred": row.pred, "correct": row.correct,
                     "shap_s": shap_s, "lime_s": lime_s})
        if i % 50 == 0:
            print(f"{i}/{len(sample)} shap {shap_s * 1000:.1f} ms  lime {lime_s:.2f} s", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "explanation_times_retime.csv", index=False)


def lime_stability(per_class=25, seeds=(1, 2), sizes=(2000, 10000)):
    """Sensitivity analysis (not the primary result): LIME |weights| for two extra seeds at
    2000 and 10000 perturbations on the first 25 sampled URLs per class, saved in long form."""
    check_frozen()
    model, cols, df, X, _ = load()
    sample = pd.read_csv(OUT / "xai_sample.csv").groupby("pred", group_keys=False).head(per_class)
    train_rows = df.index[(df["split"] == "train").to_numpy()]
    background = X.loc[train_rows].sample(n=LIME_BACKGROUND, random_state=SEED).to_numpy()

    def predict_fn(a):
        return model.predict_proba(pd.DataFrame(a, columns=cols))

    explainers = {s: LimeTabularExplainer(background, feature_names=cols, class_names=CLASSES,
                                          discretize_continuous=True, mode="classification",
                                          random_state=s) for s in seeds}
    frames = []
    for row in sample.itertuples(index=False):
        cls = CLASSES.index(row.pred)
        x = X.loc[row.row_id].to_numpy()
        for n in sizes:
            for s in seeds:
                exp = explainers[s].explain_instance(x, predict_fn, num_features=len(cols),
                                                     labels=(cls,), num_samples=n)
                weights = dict(exp.as_map()[cls])
                frames.append(pd.DataFrame({"row_id": row.row_id, "pred": row.pred, "seed": s,
                                            "num_samples": n, "feature": cols,
                                            "abs_value": [abs(weights.get(j, 0.0)) for j in range(len(cols))]}))
    pd.concat(frames).to_csv(OUT / "lime_stability.csv", index=False)
    print(f"Saved LIME stability runs for {len(sample)} URLs.")


def append(path, frame):
    frame.to_csv(path, mode="a", header=not path.exists(), index=False)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=int, default=0, help="explain only the first N sampled URLs into pilot files")
    parser.add_argument("--retime", action="store_true",
                        help="timing-only pass (explanations discarded) into explanation_times_retime.csv")
    parser.add_argument("--stability", action="store_true",
                        help="LIME seed/sample-size sensitivity on 25 URLs per class into lime_stability.csv")
    args = parser.parse_args(argv)
    if args.retime:
        return retime()
    if args.stability:
        return lime_stability()
    OUT.mkdir(parents=True, exist_ok=True)
    check_frozen()

    model, cols, df, X, preds = load()
    sample = freeze_sample(df, preds)
    class_index = {c: i for i, c in enumerate(CLASSES)}
    if args.pilot:
        sample = sample.groupby("pred", group_keys=False).head(max(args.pilot // len(CLASSES), 1))
    suffix = "_pilot" if args.pilot else ""
    paths = {m: OUT / f"{m}_explanations{suffix}.csv" for m in ("shap", "lime")}
    times_path = OUT / f"explanation_times{suffix}.csv"
    done = set(pd.read_csv(times_path)["row_id"]) if times_path.exists() else set()

    train_rows = df.index[(df["split"] == "train").to_numpy()]
    background = X.loc[train_rows].sample(n=LIME_BACKGROUND, random_state=SEED).to_numpy()
    lime_explainer = LimeTabularExplainer(
        background, feature_names=cols, class_names=CLASSES, discretize_continuous=True,
        mode="classification", random_state=SEED)
    booster = model.get_booster()

    def predict_fn(a):
        return model.predict_proba(pd.DataFrame(a, columns=cols))

    # Warm both explainers on a URL outside the sample before timing.
    warm_row = X.loc[[int(preds.loc[~preds["row_id"].isin(sample["row_id"]), "row_id"].iloc[0])]]
    tree_shap(booster, warm_row)
    lime_explainer.explain_instance(warm_row.to_numpy()[0], predict_fn, num_features=len(cols),
                                    labels=(0,), num_samples=LIME_SAMPLES)

    # Additivity: contributions + bias reproduce the margin; softmax of margins gives predict_proba.
    check = X.loc[sample["row_id"].head(50)]
    contribs = tree_shap(booster, check)
    margin = booster.predict(xgboost.DMatrix(check), output_margin=True)
    assert np.allclose(contribs.sum(axis=2), margin, atol=1e-3), "SHAP additivity check failed"
    soft = np.exp(margin - margin.max(axis=1, keepdims=True))
    assert np.allclose(soft / soft.sum(axis=1, keepdims=True), model.predict_proba(check), atol=1e-4)

    t_start = time.perf_counter()
    for i, row in enumerate(sample.itertuples(index=False), 1):
        if row.row_id in done:
            continue
        cls = class_index[row.pred]
        x = X.loc[[row.row_id]]

        t0 = time.perf_counter()
        shap_vec = tree_shap(booster, x)[0, cls, :-1]
        shap_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        exp = lime_explainer.explain_instance(x.to_numpy()[0], predict_fn, num_features=len(cols),
                                              labels=(cls,), num_samples=LIME_SAMPLES)
        lime_s = time.perf_counter() - t0
        lime_map = dict(exp.as_map()[cls])
        lime_vec = np.array([lime_map.get(j, 0.0) for j in range(len(cols))])

        for method, vec in (("shap", shap_vec), ("lime", lime_vec)):
            append(paths[method], pd.DataFrame({
                "row_id": row.row_id, "pred": row.pred, "feature": cols,
                "value": vec, "abs_value": np.abs(vec)}))
        append(OUT / f"lime_fit{suffix}.csv", pd.DataFrame([{
            "row_id": row.row_id, "pred": row.pred, "local_r2": exp.score,
            "intercept": exp.intercept[cls], "local_pred": float(np.ravel(exp.local_pred)[0])}]))
        append(times_path, pd.DataFrame([{
            "row_id": row.row_id, "pred": row.pred, "correct": row.correct,
            "shap_s": shap_s, "lime_s": lime_s}]))
        if i % 25 == 0 or args.pilot:
            print(f"{i}/{len(sample)} shap {shap_s * 1000:.1f} ms  lime {lime_s:.2f} s", flush=True)

    meta = {"per_class": PER_CLASS, "n_sample": int(len(sample)), "lime_num_samples": LIME_SAMPLES,
            "lime_background_rows": LIME_BACKGROUND, "lime_discretize_continuous": True,
            "shap_explainer": ("exact path-dependent TreeSHAP via xgboost Booster.predict(pred_contribs=True); "
                               "shap 0.49.1 TreeExplainer cannot parse xgboost 3.x vector base_score"),
            "shap_output_space": "margin (log-odds)",
            "lime_output_space": "probability", "seed": SEED, "pilot": bool(args.pilot),
            "elapsed_s_this_run": round(time.perf_counter() - t_start, 1), **environment()}
    with open(OUT / f"explain_metadata{suffix}.json", "w") as f:
        json.dump(meta, f, indent=2)
    if args.pilot:
        t = pd.read_csv(times_path)
        est = (t["shap_s"].median() + t["lime_s"].median()) * PER_CLASS * len(CLASSES)
        print(f"Pilot medians: shap {t['shap_s'].median() * 1000:.1f} ms, lime {t['lime_s'].median():.2f} s;"
              f" estimated full run {est / 60:.1f} min")


if __name__ == "__main__":
    main()
