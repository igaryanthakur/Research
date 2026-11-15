from itertools import combinations, permutations

import numpy as np
import pytest

from src.explain_v3 import (
    ART, StackModel, chance_jaccard, coalition_keep, exact_shapley, jaccard, mask, segments,
    top_k, units,
)
from src.features_v3 import FEATURE_NAMES_V3_LEXICAL, extract_features_v3_lexical

URL = "paypal.com/account/verify?id=123"


def seg_text(url):
    return [url[a:b] for a, b in segments(url)]


def test_segments_example():
    assert seg_text(URL) == ["paypal", "com", "account", "verify", "id", "123"]
    assert seg_text("a_b-c.d") == ["a", "b", "c", "d"]
    assert seg_text("caf\u00e9.fr") == ["caf", "fr"]
    assert segments("") == [] and segments("./?=") == []


def test_mask_keeps_punctuation_and_never_merges():
    u = units(URL)
    n = len(u)
    assert mask(URL, u, [True] * n) == URL
    assert mask(URL, u, [False] * n) == ".//?="
    assert mask(URL, u, [False, True, True, True, True, True]) == ".com/account/verify?id=123"
    assert mask(URL, u, [True, True, False, True, True, True], "placeholder") == \
        "paypal.com/xxxxxxx/verify?id=123"
    for bits in range(2 ** n):
        keep = coalition_keep(bits, n)
        rebuilt = mask(URL, u, keep)
        assert [c for c in rebuilt if not c.isalnum()] == [c for c in URL if not c.isalnum()]
        assert len(segments(rebuilt)) == sum(keep)


def test_merge_rule_gives_ten_contiguous_groups():
    url = "/".join(f"s{i}" for i in range(23))
    u = units(url)
    assert len(u) == 10
    flat = [span for unit in u for span in unit]
    assert flat == segments(url)
    assert all(len(unit) >= 2 for unit in u)
    assert len(units(URL)) == 6 and all(len(unit) == 1 for unit in units(URL))


def toy_value(n, weights, interaction):
    """A non-additive toy game: linear part plus an interaction between units 0 and 1."""
    vals = np.zeros(2 ** n)
    for b in range(2 ** n):
        keep = coalition_keep(b, n)
        vals[b] = sum(w for w, k in zip(weights, keep) if k) + interaction * (keep[0] and keep[1])
    return vals


def test_shapley_additivity_symmetry_and_brute_force():
    n = 6
    weights = [0.3, 0.3, -0.1, 0.0, 0.05, 0.2]
    vals = toy_value(n, weights, interaction=0.4)
    phi = exact_shapley(vals, n)
    assert np.isclose(phi.sum(), vals[-1] - vals[0])
    assert np.isclose(phi[0], phi[1])                     # symmetric players
    assert np.isclose(phi[3], 0.0)                        # dummy player
    assert np.allclose(phi[[0, 1]], 0.3 + 0.2)            # interaction split equally
    brute = np.zeros(n)
    for order in permutations(range(n)):
        bits = 0
        for i in order:
            brute[i] += vals[bits | 1 << i] - vals[bits]
            bits |= 1 << i
    assert np.allclose(phi, brute / len(list(permutations(range(n)))))


def test_chance_jaccard_matches_brute_force():
    for n in range(6, 11):
        subsets = list(combinations(range(n), 3))
        brute = np.mean([jaccard(a, b) for a in subsets for b in subsets])
        assert np.isclose(chance_jaccard(n, 3), brute)
    assert round(chance_jaccard(36, 5), 3) == 0.082


def test_top_k_tie_break_by_position():
    assert top_k([0.1, -0.5, 0.5, 0.2], 3) == [1, 2, 3]


def test_empty_url_lexical_features_finite():
    row = extract_features_v3_lexical("")
    assert len(row) == len(FEATURE_NAMES_V3_LEXICAL) and np.isfinite(row).all()


@pytest.mark.skipif(not (ART / "final_model.joblib").exists(), reason="V3 artifacts not present")
def test_empty_and_skeleton_strings_score_finite():
    model = StackModel()
    proba = model.predict_proba(["", "./?=", ".com/", URL])
    assert proba.shape == (4, 4) and np.isfinite(proba).all()
    assert np.allclose(proba.sum(axis=1), 1)
