"""Dataset audit, cleaning and fixed stratified splitting."""
import pandas as pd
from sklearn.model_selection import train_test_split

from src.features import hostname, normalize_url

SEED = 42
CLASSES = ["benign", "defacement", "malware", "phishing"]


def load_raw(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    assert list(df.columns) == ["url", "type"], f"unexpected columns: {list(df.columns)}"
    assert df.notna().all().all(), "dataset contains missing values"
    assert set(df["type"]) == set(CLASSES), f"unexpected labels: {set(df['type'])}"
    return df


def clean(df: pd.DataFrame):
    """Normalize URLs, drop every URL with conflicting labels, keep one row per normalized URL.

    Returns (clean_df with columns url_raw, url_norm, label; audit dict).
    """
    out = pd.DataFrame({"url_raw": df["url"].str.strip(), "label": df["type"]})
    out["url_norm"] = out["url_raw"].map(normalize_url)

    audit = {
        "rows_raw": int(len(df)),
        "class_counts_raw": df["type"].value_counts().to_dict(),
        "duplicate_rows_raw_url": int(df["url"].duplicated().sum()),
        "conflicting_urls_raw": int((df.groupby("url")["type"].nunique() > 1).sum()),
    }

    empty = out["url_norm"] == ""
    out = out[~empty]

    labels_per_url = out.groupby("url_norm")["label"].nunique()
    conflicting = labels_per_url[labels_per_url > 1].index
    conflict_mask = out["url_norm"].isin(conflicting)
    audit.update({
        "empty_after_normalization": int(empty.sum()),
        "conflicting_urls_normalized": int(len(conflicting)),
        "rows_removed_conflicts": int(conflict_mask.sum()),
    })
    out = out[~conflict_mask]

    before = len(out)
    out = out.drop_duplicates("url_norm", keep="first").reset_index(drop=True)
    audit.update({
        "rows_removed_duplicates_normalized": int(before - len(out)),
        "rows_clean": int(len(out)),
        "class_counts_clean": out["label"].value_counts().to_dict(),
        "url_len_summary_clean": out["url_norm"].str.len().describe().round(2).to_dict(),
    })
    return out[["url_raw", "url_norm", "label"]], audit


def assign_splits(df: pd.DataFrame) -> pd.Series:
    """Stratified 70/15/15 train/val/test labels, aligned with df.index."""
    idx_train, idx_rest = train_test_split(
        df.index, test_size=0.30, stratify=df["label"], random_state=SEED)
    idx_val, idx_test = train_test_split(
        idx_rest, test_size=0.50, stratify=df.loc[idx_rest, "label"], random_state=SEED)
    split = pd.Series("train", index=df.index)
    split[idx_val] = "val"
    split[idx_test] = "test"
    return split


def hostname_overlap(df: pd.DataFrame) -> dict:
    """Share of val/test rows whose hostname also appears in train (reported as a limitation)."""
    host = df["url_norm"].map(hostname)
    train_hosts = set(host[df["split"] == "train"])
    return {
        s: round(float(host[df["split"] == s].isin(train_hosts).mean()), 4) for s in ("val", "test")
    }
