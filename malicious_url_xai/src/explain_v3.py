"""URL-segment explanations of the full V3 stack (see documentation/v3_protocol.md).

A URL is cut into units (runs of ASCII letters/digits, at most 10 after merging), some units
are masked, the URL text is rebuilt, all 348 features are recomputed and the complete stack is
called. Exact Shapley values and LIME both explain v(S) = P(predicted class | rebuilt URL).
"""
from __future__ import annotations

import json
import re
from math import comb, factorial
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lime.lime_base import LimeBase
from scipy.stats import spearmanr
from sklearn.metrics.pairwise import pairwise_distances

from src.features_v3 import build_feature_frame_v3_lexical

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts" / "v3"

SEGMENT_RE = re.compile(r"[A-Za-z0-9]+")
MAX_UNITS = 10
MIN_SEGMENTS = 6
LIME_KERNEL_WIDTH = 25


# ---------------------------------------------------------------- units and masking

def segments(url: str) -> list[tuple[int, int]]:
    """(start, end) spans of every maximal ASCII letter/digit run."""
    return [m.span() for m in SEGMENT_RE.finditer(url)]


def units(url: str, max_units: int = MAX_UNITS) -> list[list[tuple[int, int]]]:
    """Segments grouped into at most max_units contiguous units."""
    segs = segments(url)
    if len(segs) <= max_units:
        return [[s] for s in segs]
    return [[segs[i] for i in idx] for idx in np.array_split(np.arange(len(segs)), max_units)]


def mask(url: str, unit_spans, keep, rule: str = "delete") -> str:
    """Rebuild url with every unit whose keep flag is false masked; punctuation is never touched."""
    spans = sorted(span for unit, k in zip(unit_spans, keep) if not k for span in unit)
    out, pos = [], 0
    for start, end in spans:
        out.append(url[pos:start])
        if rule == "placeholder":
            out.append("x" * (end - start))
        elif rule != "delete":
            raise ValueError(rule)
        pos = end
    out.append(url[pos:])
    return "".join(out)


def unit_text(url: str, unit) -> str:
    """Text of one unit: from its first segment to its last, inner punctuation included."""
    return url[unit[0][0]:unit[-1][1]]


def coalition_keep(bits: int, n: int) -> list[bool]:
    """Unit i is kept when bit i of the coalition index is set."""
    return [bool(bits >> i & 1) for i in range(n)]


# ---------------------------------------------------------------- model

class StackModel:
    """The frozen V3 stack applied to raw URL strings (no normalization inside)."""

    def __init__(self, art: Path = ART):
        bundle = joblib.load(art / "final_model.joblib")
        assert "meta" in bundle and "bases" in bundle, "expected the V3 stacking bundle"
        self.meta, self.bases, self.families = bundle["meta"], bundle["bases"], bundle["families"]
        if "xgb" in self.bases:
            self.bases["xgb"].set_params(device="cpu")
        self.vectorizer = joblib.load(art / "ngram_vectorizer.joblib")
        self.columns = json.loads((art / "feature_names.json").read_text())
        self.ngram_names = [f"ng_{g}" for g in self.vectorizer.get_feature_names_out()]
        self.calls = 0

    def featurize(self, urls) -> pd.DataFrame:
        urls = list(urls)
        lexical = build_feature_frame_v3_lexical(urls).astype(np.float32)
        ngram = pd.DataFrame(self.vectorizer.transform(urls).toarray(),
                             columns=self.ngram_names, dtype=np.float32)
        return pd.concat([lexical, ngram], axis=1)[self.columns]

    def predict_proba(self, urls) -> np.ndarray:
        x = self.featurize(urls).to_numpy(dtype=np.float32)
        self.calls += len(x)
        blocks = [np.asarray(self.bases[f].predict_proba(x), dtype=np.float64) for f in self.families]
        return self.meta.predict_proba(np.hstack(blocks))


# ---------------------------------------------------------------- explainers

def coalition_values(value_fn, url, unit_spans, rule="delete"):
    """v(S) for every coalition S, indexed by bitmask; also returns the rebuilt strings."""
    n = len(unit_spans)
    strings = [mask(url, unit_spans, coalition_keep(b, n), rule) for b in range(2 ** n)]
    return np.asarray(value_fn(strings), dtype=np.float64), strings


def exact_shapley(values: np.ndarray, n: int) -> np.ndarray:
    """Exact Shapley values from a 2**n table of coalition values indexed by bitmask."""
    assert len(values) == 2 ** n
    bits = np.arange(2 ** n)
    sizes = np.array([bin(b).count("1") for b in bits])
    weight = np.array([factorial(s) * factorial(n - s - 1) / factorial(n) if s < n else 0.0
                       for s in range(n + 1)])
    phi = np.zeros(n)
    for i in range(n):
        without = bits[(bits >> i & 1) == 0]
        phi[i] = np.sum(weight[sizes[without]] * (values[without | (1 << i)] - values[without]))
    return phi


def lime_segments(value_fn, url, unit_spans, num_samples, seed, rule="delete"):
    """LIME on unit masks, sampling exactly as lime 0.2.0.1 LimeTextExplainer does."""
    n = len(unit_spans)
    rs = np.random.RandomState(seed)
    data = np.ones((num_samples, n))
    sizes = rs.randint(1, n + 1, num_samples - 1)
    for i, size in enumerate(sizes, start=1):
        data[i, rs.choice(range(n), size, replace=False)] = 0
    strings = [mask(url, unit_spans, row.astype(bool), rule) for row in data]
    labels = np.asarray(value_fn(strings), dtype=np.float64).reshape(-1, 1)
    distances = pairwise_distances(data, data[0].reshape(1, -1), metric="cosine").ravel() * 100

    def kernel(d):
        return np.sqrt(np.exp(-(d ** 2) / LIME_KERNEL_WIDTH ** 2))

    base = LimeBase(kernel, random_state=seed)
    intercept, exp, score, local_pred = base.explain_instance_with_data(
        data, labels, distances, label=0, num_features=n, feature_selection="none")
    weights = np.zeros(n)
    for j, w in exp:
        weights[j] = w
    return {"weights": weights, "r2": float(score), "intercept": float(intercept),
            "local_pred": float(np.ravel(local_pred)[0]), "calls": num_samples}


# ---------------------------------------------------------------- agreement helpers

def top_k(values, k: int = 3) -> list[int]:
    """Indices of the k largest |values|; exact ties broken by unit position."""
    return sorted(range(len(values)), key=lambda i: (-abs(values[i]), i))[:k]


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b)


def chance_jaccard(n: int, k: int = 3) -> float:
    """Exact expected Jaccard of two independent uniformly random k-subsets of n items."""
    total = comb(n, k)
    return sum(comb(k, h) * comb(n - k, k - h) / total * h / (2 * k - h) for h in range(k + 1))


def pair_agreement(a, b, k: int = 3) -> dict:
    """Agreement of two explanations of the same units (protocol section 4 and Amendment A1.6).

    jaccard: top-k Jaccard by |value|. spearman: rank correlation of |value| over all units, NaN
    when either vector is constant. sign_agreement: share of the units in both top-k sets whose
    two values have the same sign, NaN when no unit is shared.
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    top_a, top_b = top_k(a, k), top_k(b, k)
    abs_a, abs_b = np.abs(a), np.abs(b)
    constant = np.ptp(abs_a) == 0 or np.ptp(abs_b) == 0
    shared = sorted(set(top_a) & set(top_b))
    return {
        "jaccard": jaccard(top_a, top_b),
        "spearman": float("nan") if constant else float(spearmanr(abs_a, abs_b).statistic),
        "n_shared": len(shared),
        "sign_agreement": (float(np.mean([np.sign(a[i]) == np.sign(b[i]) for i in shared]))
                           if shared else float("nan")),
        "top_a": top_a, "top_b": top_b,
    }
