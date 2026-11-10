import numpy as np
import pytest

from src.features import normalize_url
from src.features_v2 import FEATURE_NAMES_V2, extract_features_v2
from src.features_v3 import (
    FEATURE_NAMES_V3_LEXICAL,
    TOP_BRANDS,
    build_feature_frame_v3_lexical,
    extract_features_v3_lexical,
)


def feats(url):
    return dict(zip(FEATURE_NAMES_V3_LEXICAL, extract_features_v3_lexical(url)))


def test_schema_extends_v2():
    assert FEATURE_NAMES_V3_LEXICAL[:len(FEATURE_NAMES_V2)] == FEATURE_NAMES_V2
    assert len(FEATURE_NAMES_V3_LEXICAL) == len(set(FEATURE_NAMES_V3_LEXICAL))
    assert len(extract_features_v3_lexical("a.com/x")) == len(FEATURE_NAMES_V3_LEXICAL)


def test_v2_prefix_identity():
    url = "secure.example.com/path?x=1#frag"
    v2 = extract_features_v2(url)
    v3 = extract_features_v3_lexical(url)
    assert v3[:len(v2)] == v2


def test_no_scheme_www_leak_names():
    for name in FEATURE_NAMES_V3_LEXICAL:
        assert not any(bad in name for bad in ("http", "https", "scheme", "www"))


def test_segmented_entropy_differs():
    f = feats("google.com/a8f9c0e2b1d3/payload?token=ZZZZYYYYXXXX")
    assert f["host_entropy"] > 0
    assert f["path_entropy"] > f["host_entropy"] or f["query_entropy"] > 0
    assert f["entropy_host_path_absdiff"] == abs(f["host_entropy"] - f["path_entropy"])


def test_brand_typosquat_flag():
    f = feats("secure.paypa1.com/login")
    assert f["min_brand_edit_distance"] == 1
    assert f["brand_typo_flag"] == 1
    assert f["is_exact_brand_host"] == 0


def test_exact_brand_host():
    f = feats("paypal.com/home")
    assert f["min_brand_edit_distance"] == 0
    assert f["is_exact_brand_host"] == 1
    assert f["brand_typo_flag"] == 0


def test_brand_in_subdomain_and_path():
    f = feats("paypal.evil-secure.tk/account")
    assert f["brand_in_subdomain"] == 1
    g = feats("evil.tk/paypal/login")
    assert g["brand_in_path_or_query"] == 1
    assert g["is_exact_brand_host"] == 0


def test_brands_are_reasonable():
    assert "paypal" in TOP_BRANDS and "microsoft" in TOP_BRANDS
    assert all(len(b) >= 3 for b in TOP_BRANDS)


@pytest.mark.parametrize("url", [
    "", "10.0.0.1/x", "xn--pple-43d.com", "a.com/%41", "user@evil.com/p",
])
def test_finite_deterministic(url):
    a = extract_features_v3_lexical(url)
    b = extract_features_v3_lexical(url)
    assert a == b and np.isfinite(a).all()


def test_normalization_invariance():
    base = feats(normalize_url("example.com/a?b=1"))
    for raw in ("http://www.example.com/a?b=1", "HTTPS://WWW.example.com/a?b=1"):
        assert feats(normalize_url(raw)) == base


def test_frame_builder():
    df = build_feature_frame_v3_lexical(["a.com", "b.com/login"])
    assert list(df.columns) == FEATURE_NAMES_V3_LEXICAL
    assert df.shape == (2, len(FEATURE_NAMES_V3_LEXICAL))
