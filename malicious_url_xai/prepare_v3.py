"""V3 stage 1: reuse the frozen V2 clean split; cache lexical + char-ngram TF-IDF features.

N-gram vocabulary is fit on the training split only (no val/test leakage).
"""
import hashlib
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from src.data import CLASSES
from src.features_v2 import FEATURE_NAMES_V2
from src.features_v3 import (
    FEATURE_NAMES_V3_LEXICAL,
    build_feature_frame_v3_lexical,
    feature_manifest_v3,
)
from src.runinfo import environment, peak_memory_mb

ROOT = Path(__file__).resolve().parent
ART_V2 = ROOT / "artifacts" / "v2"
ART = ROOT / "artifacts" / "v3"
RES = ROOT / "results" / "v3"

NGRAM_MAX_FEATURES = 300
NGRAM_RANGE = (3, 4)
NGRAM_MIN_DF = 5
EXPECTED_SPLIT = {"train": 441_825, "val": 94_677, "test": 94_677}


def main():
    if not (ART_V2 / "clean.parquet").exists():
        raise SystemExit("Missing artifacts/v2/clean.parquet. Run python prepare_v2.py first.")

    ART.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    timings = {}

    t0 = time.perf_counter()
    df = pd.read_parquet(ART_V2 / "clean.parquet")
    timings["load_clean_s"] = round(time.perf_counter() - t0, 1)

    sizes = df["split"].value_counts().to_dict()
    assert sizes == EXPECTED_SPLIT, sizes
    assert set(df["label"]) == set(CLASSES)
    assert list(df.columns) == ["url_raw", "url_norm", "label", "split"] or set(
        ["url_raw", "url_norm", "label", "split"]
    ).issubset(df.columns)

    # Keep a local copy so V3 is self-contained.
    df.to_parquet(ART / "clean.parquet")

    train_mask = df["split"] == "train"
    assert int(train_mask.sum()) == EXPECTED_SPLIT["train"]

    t0 = time.perf_counter()
    x_lex = build_feature_frame_v3_lexical(df["url_norm"], index=df.index)
    timings["extract_lexical_s"] = round(time.perf_counter() - t0, 1)
    assert list(x_lex.columns) == FEATURE_NAMES_V3_LEXICAL
    assert np.isfinite(x_lex.to_numpy()).all()
    # Prefix continuity with V2 lexical columns.
    if (ART_V2 / "features_v2_norm.parquet").exists():
        x2 = pd.read_parquet(ART_V2 / "features_v2_norm.parquet")
        np.testing.assert_array_equal(x_lex[FEATURE_NAMES_V2].to_numpy(), x2[FEATURE_NAMES_V2].to_numpy())

    x_lex.to_parquet(ART / "features_v3_lexical.parquet")

    t0 = time.perf_counter()
    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=NGRAM_RANGE,
        max_features=NGRAM_MAX_FEATURES,
        min_df=NGRAM_MIN_DF,
        lowercase=True,
        dtype=np.float32,
        sublinear_tf=True,
    )
    vectorizer.fit(df.loc[train_mask, "url_norm"])
    timings["fit_ngram_s"] = round(time.perf_counter() - t0, 1)

    t0 = time.perf_counter()
    ngram_sparse = vectorizer.transform(df["url_norm"])
    ngram_names = [f"ng_{g}" for g in vectorizer.get_feature_names_out()]
    x_ng = pd.DataFrame(
        ngram_sparse.toarray(),
        columns=ngram_names,
        index=df.index,
        dtype=np.float32,
    )
    timings["transform_ngram_s"] = round(time.perf_counter() - t0, 1)
    assert x_ng.shape[1] == len(ngram_names) <= NGRAM_MAX_FEATURES
    assert np.isfinite(x_ng.to_numpy()).all()

    t0 = time.perf_counter()
    x_full = pd.concat([x_lex.astype(np.float32), x_ng], axis=1)
    timings["concat_s"] = round(time.perf_counter() - t0, 1)
    assert list(x_full.columns) == FEATURE_NAMES_V3_LEXICAL + ngram_names
    x_full.to_parquet(ART / "features_v3_full.parquet")
    x_ng.to_parquet(ART / "features_v3_ngram.parquet")
    joblib.dump(vectorizer, ART / "ngram_vectorizer.joblib")

    # Train-only distribution summary for new lexical columns.
    new_cols = FEATURE_NAMES_V3_LEXICAL[len(FEATURE_NAMES_V2):]
    rows, dropped = [], {}
    for col in new_cols:
        values = x_lex.loc[train_mask, col]
        top_share = float(values.value_counts(normalize=True).iloc[0])
        rows.append({
            "feature": col,
            "n_unique": int(values.nunique()),
            "top_value_share": round(top_share, 5),
            **{f"mean_{c}": round(float(values[df.loc[train_mask, "label"] == c].mean()), 4)
               for c in CLASSES},
        })
        if values.nunique() <= 1:
            dropped[col] = "constant on train"
    pd.DataFrame(rows).to_csv(RES / "feature_summary_train.csv", index=False)

    manifest = feature_manifest_v3(ngram_names=ngram_names, dropped=dropped)
    manifest["ngram"] = {
        "analyzer": "char",
        "ngram_range": list(NGRAM_RANGE),
        "max_features": NGRAM_MAX_FEATURES,
        "min_df": NGRAM_MIN_DF,
        "sublinear_tf": True,
        "fit_split": "train",
        "n_features_actual": len(ngram_names),
    }
    manifest["feature_hash"] = hashlib.sha256(
        json.dumps(manifest["feature_names"]).encode()
    ).hexdigest()
    with open(ART / "feature_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    audit = {
        "source_clean": str(ART_V2 / "clean.parquet"),
        "rows": int(len(df)),
        "split_counts": sizes,
        "n_lexical_features": len(FEATURE_NAMES_V3_LEXICAL),
        "n_ngram_features": len(ngram_names),
        "n_features_full": int(x_full.shape[1]),
        "dropped_features": dropped,
        "timings": timings,
        "peak_memory_mb": peak_memory_mb(),
        "environment": environment(),
        "feature_hash": manifest["feature_hash"],
    }
    with open(RES / "data_audit.json", "w") as f:
        json.dump(audit, f, indent=2)

    print(json.dumps({k: audit[k] for k in (
        "rows", "split_counts", "n_lexical_features", "n_ngram_features",
        "n_features_full", "dropped_features", "timings", "peak_memory_mb",
    )}, indent=2))
    print(pd.DataFrame(rows).to_string(index=False))
    print("Top n-grams:", ngram_names[:20])


if __name__ == "__main__":
    main()
