"""Stage 1: audit + clean the dataset, assign the fixed split, cache lexical features."""
import json
import time
from pathlib import Path

from src.data import assign_splits, clean, hostname_overlap, load_raw
from src.features import build_feature_frame

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "malicious_phish.csv"
ART = ROOT / "artifacts"
RES = ROOT / "results"


def main():
    ART.mkdir(exist_ok=True)
    RES.mkdir(exist_ok=True)

    t0 = time.perf_counter()
    df, audit = clean(load_raw(DATA))
    df["split"] = assign_splits(df)
    audit["split_counts"] = {
        s: df.loc[df["split"] == s, "label"].value_counts().to_dict() for s in ("train", "val", "test")
    }
    audit["hostname_overlap_with_train"] = hostname_overlap(df)
    df.to_parquet(ART / "clean.parquet")
    print(json.dumps(audit, indent=2))

    print("Extracting normalized-URL features...")
    build_feature_frame(df["url_norm"]).to_parquet(ART / "features_norm.parquet")
    print("Extracting raw-URL features (ablation)...")
    build_feature_frame(df["url_raw"], raw=True).to_parquet(ART / "features_raw.parquet")

    with open(RES / "data_audit.json", "w") as f:
        json.dump(audit, f, indent=2)
    print(f"Done in {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
