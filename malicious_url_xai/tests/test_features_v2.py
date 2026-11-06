import numpy as np
import pandas as pd
import pytest

from src.features import FEATURE_NAMES, build_feature_frame, normalize_url
from src.features_v2 import (FEATURE_NAMES_V2, LEXICON_FEATURES, STRUCTURAL_FEATURES,
                             build_feature_frame_v2, extract_features_v2, feature_manifest)


def feats(url):
    return dict(zip(FEATURE_NAMES_V2, extract_features_v2(url)))


def test_schema_order_and_length():
    assert FEATURE_NAMES_V2[:len(FEATURE_NAMES)] == FEATURE_NAMES
    assert FEATURE_NAMES_V2 == FEATURE_NAMES + STRUCTURAL_FEATURES + LEXICON_FEATURES
    assert len(FEATURE_NAMES_V2) == len(set(FEATURE_NAMES_V2)) == 39
    assert len(extract_features_v2("a.com/x")) == 39


def test_no_scheme_or_www_features():
    for name in FEATURE_NAMES_V2:
        assert not any(bad in name for bad in ("http", "https", "scheme", "www"))


@pytest.mark.parametrize("url", [
    "example.com/a/b?x=1#frag", "", "http://[::1", "[::1]:8080/a", "192.168.0.1:8080/x",
    "a.com/%zz%41", "xn--80ak6aa92e.com/login", "пример.рф/путь", "a.com:99999/p",
    "////", "?#", "user@evil.com:80/p",
])
def test_finite_deterministic(url):
    a, b = extract_features_v2(url), extract_features_v2(url)
    assert a == b and len(a) == 39 and np.isfinite(a).all()


def test_path_segments():
    f = feats("a.com/abc/defghij//x")
    assert f["first_dir_len"] == 3 and f["longest_path_segment_len"] == 7
    g = feats("a.com")
    assert g["first_dir_len"] == 0 and g["longest_path_segment_len"] == 0


def test_host_labels_and_ip_hosts():
    f = feats("mail.google.co.uk/x")
    assert f["tld_len"] == 2 and f["host_label_count"] == 4 and f["max_host_label_len"] == 6
    for url in ("10.0.0.1/login", "[2001:db8::1]:443/x"):
        g = feats(url)
        assert g["tld_len"] == g["host_label_count"] == g["max_host_label_len"] == 0


def test_fragment_and_embedded_double_slash():
    f = feats("a.com/redirect?u=http://b.com/x#top")
    assert f["fragment_len"] == 3 and f["embedded_double_slash_count"] == 1
    assert feats("a.com/x//y")["embedded_double_slash_count"] == 1
    assert feats("a.com/x")["embedded_double_slash_count"] == 0


def test_suspicious_tokens_exact_and_case_insensitive():
    assert feats("a.com/LOGIN/Verify-account")["suspicious_token_count"] == 3
    assert feats("a.com/mylogin/accounting")["suspicious_token_count"] == 0
    assert feats("paypal.com.secure-update.xyz")["suspicious_token_count"] == 3


def test_shortener_exact_host():
    assert feats("bit.ly/abc")["is_shortener_host"] == 1
    assert feats("BIT.LY/abc")["is_shortener_host"] == 1
    assert feats("notbit.ly.example.com/x")["is_shortener_host"] == 0
    assert feats("bit.ly.evil.com")["is_shortener_host"] == 0


def test_punycode():
    assert feats("xn--pple-43d.com")["has_punycode"] == 1
    assert feats("sub.xn--pple-43d.com")["has_punycode"] == 1
    assert feats("apple.com")["has_punycode"] == 0


def test_scheme_and_www_invariance_after_normalization():
    base = feats(normalize_url("example.com/a?b=1"))
    for raw in ("http://www.example.com/a?b=1", "HTTPS://WWW.example.com/a?b=1", "www.example.com/a?b=1"):
        assert feats(normalize_url(raw)) == base


def test_prefix_matches_v1_and_frame_stability():
    urls = ["a.com/x?y=1", "http://[::1", "", "bit.ly/q", "x" * 300]
    idx = pd.Index([10, 3, 7, 1, 99])
    v2 = build_feature_frame_v2(urls, index=idx)
    assert list(v2.columns) == FEATURE_NAMES_V2 and list(v2.index) == list(idx)
    v1 = build_feature_frame(urls)
    np.testing.assert_array_equal(v2[FEATURE_NAMES].to_numpy(), v1.to_numpy())
    pd.testing.assert_frame_equal(v2, build_feature_frame_v2(urls, index=idx))


def test_manifest_contents():
    m = feature_manifest()
    assert m["feature_names"] == FEATURE_NAMES_V2
    assert set(m["definitions_new"]) == set(STRUCTURAL_FEATURES + LEXICON_FEATURES)
    assert "bit.ly" in m["shortener_hosts"] and "login" in m["suspicious_tokens"]
