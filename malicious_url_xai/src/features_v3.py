"""V3 lexical features: V2 schema plus segmented entropy and brand/typosquat signals.

Still leak-free: no scheme/www/http indicators, no network calls. Character n-grams are
fitted separately in prepare_v3 (train-only) and concatenated outside this module.
"""
from __future__ import annotations

import re
from datetime import datetime

import numpy as np
import pandas as pd
from rapidfuzz.distance import Levenshtein

from src.features import FEATURE_NAMES, _is_ip, _split, shannon_entropy
from src.features_v2 import (
    FEATURE_DEFINITIONS as V2_DEFINITIONS,
    FEATURE_NAMES_V2,
    LEXICON_FEATURES,
    STRUCTURAL_FEATURES,
    extract_features_v2,
)

FEATURE_VERSION = "v3.0"
NORMALIZATION_VERSION = "v1: strip whitespace, one leading scheme://, one leading www."

SEGMENT_ENTROPY_FEATURES = [
    "host_entropy",
    "path_entropy",
    "query_entropy",
    "entropy_host_path_absdiff",
]

# Curated high-value phishing targets (registered-domain labels only; lowercase ASCII).
_BRAND_CANDIDATES = (
    "google", "gmail", "youtube", "facebook", "instagram", "whatsapp", "messenger",
    "twitter", "linkedin", "microsoft", "outlook", "office", "office365",
    "microsoftonline", "live", "hotmail", "apple", "icloud", "itunes", "amazon",
    "aws", "paypal", "ebay", "netflix", "spotify", "adobe", "dropbox", "github",
    "steam", "epicgames", "binance", "coinbase", "blockchain", "chase", "wellsfargo",
    "bankofamerica", "citibank", "americanexpress", "amex", "discover", "capitalone",
    "hsbc", "barclays", "lloyds", "natwest", "revolut", "venmo", "cashapp", "zelle",
    "walmart", "target", "bestbuy", "alibaba", "aliexpress", "dhl", "fedex", "ups",
    "usps", "royalmail", "irs", "ssa", "yahoo", "aol", "protonmail", "zoom",
    "slack", "discord", "twitch", "tiktok", "snapchat", "pinterest", "reddit",
    "craigslist", "indeed", "okta", "salesforce", "docusign",
    "intuit", "turbotax", "quickbooks", "kraken", "robinhood",
)
# Deduplicate while preserving order. Exclude ultra-short labels ("x", "gov") that
# create noisy edit-distance collisions with benign hosts.
TOP_BRANDS = tuple(dict.fromkeys(b.lower() for b in _BRAND_CANDIDATES if len(b) >= 3))

BRAND_FEATURES = [
    "min_brand_edit_distance",
    "brand_typo_flag",          # 1 if 1 <= edit distance <= 2 to a brand
    "brand_in_subdomain",       # brand label appears in a non-registered host label
    "brand_in_path_or_query",   # brand token appears in path/query but not exact brand host
    "is_exact_brand_host",      # registered domain exactly matches a curated brand
]

FEATURE_NAMES_V3_LEXICAL = FEATURE_NAMES_V2 + SEGMENT_ENTROPY_FEATURES + BRAND_FEATURES

FEATURE_DEFINITIONS_V3 = {
    **V2_DEFINITIONS,
    "host_entropy": "Shannon entropy of the hostname string",
    "path_entropy": "Shannon entropy of the path string",
    "query_entropy": "Shannon entropy of the query string",
    "entropy_host_path_absdiff": "absolute difference between host_entropy and path_entropy",
    "min_brand_edit_distance": (
        "minimum Levenshtein distance between the registered domain label and TOP_BRANDS; "
        "capped at 10; 10 for IP/empty hosts"
    ),
    "brand_typo_flag": "1 if 1 <= min_brand_edit_distance <= 2",
    "brand_in_subdomain": "1 if any non-registered host label exactly equals a TOP_BRANDS entry",
    "brand_in_path_or_query": (
        "1 if a TOP_BRANDS token appears in path/query [a-z0-9]+ tokens and the host is not "
        "an exact brand registered domain"
    ),
    "is_exact_brand_host": "1 if the registered domain label exactly matches TOP_BRANDS",
}

TOKEN_RE = re.compile(r"[a-z0-9]+")
MAX_BRAND_DISTANCE = 10


def _registered_label(host: str) -> str:
    """Best-effort second-level label (e.g. 'paypal' from 'secure.paypal.com')."""
    host = host.rstrip(".").lower()
    if not host or _is_ip(host):
        return ""
    labels = [p for p in host.split(".") if p]
    if len(labels) >= 2:
        return labels[-2]
    return labels[0] if labels else ""


def _min_brand_distance(label: str) -> int:
    if not label:
        return MAX_BRAND_DISTANCE
    best = MAX_BRAND_DISTANCE
    for brand in TOP_BRANDS:
        # Skip hopeless pairs early.
        if abs(len(label) - len(brand)) >= best:
            continue
        d = Levenshtein.distance(label, brand, score_cutoff=best)
        if d < best:
            best = d
            if best == 0:
                break
    return int(best)


def extract_features_v3_lexical(url: str) -> list:
    """Lexical V3 vector in FEATURE_NAMES_V3_LEXICAL order (no TF-IDF columns)."""
    _, host, path, query = _split(url)
    host = host.rstrip(".")
    row = extract_features_v2(url)

    he = shannon_entropy(host)
    pe = shannon_entropy(path)
    qe = shannon_entropy(query)
    row += [he, pe, qe, abs(he - pe)]

    label = _registered_label(host)
    dist = _min_brand_distance(label)
    exact = int(dist == 0 and bool(label))
    typo = int(1 <= dist <= 2)

    labels = [] if _is_ip(host) else [p.lower() for p in host.split(".") if p]
    # Non-registered labels = everything except final TLD and the registered label.
    subdomain_labels = labels[:-2] if len(labels) >= 2 else []
    brand_in_sub = int(any(lab in TOP_BRANDS for lab in subdomain_labels))

    tokens = set(TOKEN_RE.findall((path + "?" + query).lower()))
    brand_in_pq = int((not exact) and any(b in tokens for b in TOP_BRANDS))

    row += [dist, typo, brand_in_sub, brand_in_pq, exact]
    assert len(row) == len(FEATURE_NAMES_V3_LEXICAL)
    return row


def build_feature_frame_v3_lexical(urls, index=None) -> pd.DataFrame:
    df = pd.DataFrame(
        [extract_features_v3_lexical(u) for u in urls],
        columns=FEATURE_NAMES_V3_LEXICAL,
        index=index,
        dtype=np.float64,
    )
    assert list(df.columns) == FEATURE_NAMES_V3_LEXICAL
    assert np.isfinite(df.to_numpy()).all(), "feature matrix contains NaN or infinity"
    return df


def feature_manifest_v3(ngram_names=None, dropped=None) -> dict:
    dropped = dropped or {}
    ngram_names = list(ngram_names or [])
    return {
        "feature_version": FEATURE_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "feature_names_lexical": FEATURE_NAMES_V3_LEXICAL,
        "feature_names_ngram": ngram_names,
        "feature_names": FEATURE_NAMES_V3_LEXICAL + ngram_names,
        "blocks": {
            "v1": FEATURE_NAMES,
            "structural": STRUCTURAL_FEATURES,
            "lexicon": LEXICON_FEATURES,
            "segment_entropy": SEGMENT_ENTROPY_FEATURES,
            "brand": BRAND_FEATURES,
            "char_ngram_tfidf": ngram_names,
        },
        "definitions_new": FEATURE_DEFINITIONS_V3,
        "top_brands": list(TOP_BRANDS),
        "max_brand_distance": MAX_BRAND_DISTANCE,
        "dropped_features": dropped,
    }
