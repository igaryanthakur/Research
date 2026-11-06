import math

import numpy as np
import pandas as pd
import pytest

from src.data import assign_splits, clean
from src.features import (FEATURE_NAMES, RAW_EXTRA_FEATURES, build_feature_frame,
                          extract_features, normalize_url, shannon_entropy)


def feats(url, raw=False):
    names = FEATURE_NAMES + (RAW_EXTRA_FEATURES if raw else [])
    return dict(zip(names, extract_features(url, raw=raw)))


@pytest.mark.parametrize("raw,expected", [
    ("http://www.example.com/a", "example.com/a"),
    ("HTTPS://WWW.Example.com/A/B", "Example.com/A/B"),
    ("  www.example.com  ", "example.com"),
    ("example.com/www.x", "example.com/www.x"),
    ("ftp://files.example.com", "files.example.com"),
])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_scheme_and_schemeless_parse_same_host_and_path():
    a = feats("http://sub.example.com/x/y?a=1&b=2")
    b = feats("sub.example.com/x/y?a=1&b=2")
    for key in ("host_len", "path_len", "query_len", "subdomain_count", "path_depth", "query_param_count"):
        assert a[key] == b[key], key
    assert b["subdomain_count"] == 1 and b["path_depth"] == 2 and b["query_param_count"] == 2


def test_ip_port_and_percent_encoding():
    f = feats("192.168.0.1:8080/login%20page")
    assert f["host_is_ip"] == 1 and f["has_port"] == 1 and f["has_pct_encoding"] == 1
    assert f["subdomain_count"] == 0
    g = feats("example.com")
    assert g["host_is_ip"] == 0 and g["has_port"] == 0 and g["has_pct_encoding"] == 0
    assert g["path_len"] == 0 and g["path_depth"] == 0


def test_raw_only_flags():
    assert feats("https://a.com", raw=True)["is_https"] == 1
    assert feats("http://a.com", raw=True)["has_scheme"] == 1
    assert feats("a.com", raw=True)["has_scheme"] == 0
    assert "is_https" not in FEATURE_NAMES and "has_scheme" not in FEATURE_NAMES


def test_entropy_and_empty_string():
    assert shannon_entropy("") == 0.0
    assert shannon_entropy("aaaa") == 0.0
    assert math.isclose(shannon_entropy("ab"), 1.0)
    f = feats("")
    assert f["digit_ratio"] == 0 and f["special_ratio"] == 0


def test_feature_frame_is_finite_and_deterministic():
    urls = ["http://[::1", "a.com/%zz", "x" * 500, "", "user@evil.com:99999/p"]
    a, b = build_feature_frame(urls), build_feature_frame(urls)
    assert list(a.columns) == FEATURE_NAMES
    assert np.isfinite(a.to_numpy()).all()
    pd.testing.assert_frame_equal(a, b)


def test_clean_removes_conflicts_and_normalized_duplicates():
    raw = pd.DataFrame({
        "url": ["http://a.com", "a.com", "www.b.com", "b.com", "c.com", "d.com"],
        "type": ["phishing", "phishing", "benign", "malware", "benign", "defacement"],
    })
    out, audit = clean(raw)
    assert sorted(out["url_norm"]) == ["a.com", "c.com", "d.com"]
    assert audit["conflicting_urls_normalized"] == 1
    assert audit["rows_removed_duplicates_normalized"] == 1


def test_splits_are_disjoint_and_stratified():
    df = pd.DataFrame({"label": ["benign"] * 700 + ["defacement"] * 100 + ["malware"] * 100 + ["phishing"] * 100})
    split = assign_splits(df)
    assert split.value_counts().to_dict() == {"train": 700, "val": 150, "test": 150}
    assert (df[split == "test"]["label"] == "malware").sum() == 15
