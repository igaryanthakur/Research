"""V2 stage 1: rebuild the cleaned data and fixed split, cache aligned V1 and V2 feature matrices."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.data import CLASSES, assign_splits, clean, hostname_overlap, load_raw
from src.features import FEATURE_NAMES, build_feature_frame
from src.features_v2 import FEATURE_NAMES_V2, build_feature_frame_v2, feature_manifest
from src.runinfo import environment, peak_memory_mb

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "malicious_phish.csv"
ART = ROOT / "artifacts" / "v2"
RES = ROOT / "results" / "v2"

EXPECTED = {"rows_raw": 651_191, "rows_clean": 631_179,
            "split": {"train": 441_825, "val": 94_677, "test": 94_677}}


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ART.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    timings = {}

    t0 = time.perf_counter()
    df, audit = clean(load_raw(DATA))
    df["split"] = assign_splits(df)
    timings["clean_split_s"] = round(time.perf_counter() - t0, 1)

    sizes = df["split"].value_counts().to_dict()
    assert audit["rows_raw"] == EXPECTED["rows_raw"], audit["rows_raw"]
    assert audit["rows_clean"] == EXPECTED["rows_clean"], audit["rows_clean"]
    assert sizes == EXPECTED["split"], sizes
    assert set(df["label"]) == set(CLASSES)
    groups = {s: set(df.index[df["split"] == s]) for s in EXPECTED["split"]}
    assert not (groups["train"] & groups["val"] or groups["train"] & groups["test"]
                or groups["val"] & groups["test"])

    audit["split_counts"] = {
        s: df.loc[df["split"] == s, "label"].value_counts().to_dict() for s in ("train", "val", "test")}
    audit["hostname_overlap_with_train"] = hostname_overlap(df)
    audit["dataset_sha256"] = file_sha256(DATA)
    df.to_parquet(ART / "clean.parquet")

    t0 = time.perf_counter()
    x1 = build_feature_frame(df["url_norm"])
    x1.index = df.index
    timings["extract_v1_s"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    x2 = build_feature_frame_v2(df["url_norm"], index=df.index)
    timings["extract_v2_s"] = round(time.perf_counter() - t0, 1)

    assert list(x1.columns) == FEATURE_NAMES and list(x2.columns) == FEATURE_NAMES_V2
    assert len(x1) == len(x2) == len(df) and x1.index.equals(df.index) and x2.index.equals(df.index)
    for x in (x1, x2):
        assert np.isfinite(x.to_numpy()).all()
    np.testing.assert_array_equal(x2[FEATURE_NAMES].to_numpy(), x1.to_numpy())

    x1.to_parquet(ART / "features_v1_norm.parquet")
    x2.to_parquet(ART / "features_v2_norm.parquet")

    # Distribution check on train rows only, for the new features.
    train = (df["split"] == "train").to_numpy()
    new_cols = FEATURE_NAMES_V2[len(FEATURE_NAMES):]
    rows, dropped = [], {}
    for col in new_cols:
        values = x2.loc[train, col]
        top_share = float(values.value_counts(normalize=True).iloc[0])
        rows.append({"feature": col, "n_unique": int(values.nunique()),
                     "top_value_share": round(top_share, 5),
                     **{f"mean_{c}": round(float(values[df.loc[train, "label"] == c].mean()), 4)
                        for c in CLASSES}})
        if values.nunique() <= 1:
            dropped[col] = "constant on train"
    pd.DataFrame(rows).to_csv(RES / "feature_summary_train.csv", index=False)

    manifest = feature_manifest(dropped)
    manifest["feature_hash"] = hashlib.sha256(json.dumps(FEATURE_NAMES_V2).encode()).hexdigest()
    with open(ART / "feature_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    audit.update({"timings": timings, "peak_memory_mb": peak_memory_mb(),
                  "environment": environment(), "dropped_features": dropped})
    with open(RES / "data_audit.json", "w") as f:
        json.dump(audit, f, indent=2)
    print(json.dumps({k: audit[k] for k in ("rows_raw", "rows_clean", "hostname_overlap_with_train",
                                            "timings", "peak_memory_mb", "dropped_features")}, indent=2))
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
