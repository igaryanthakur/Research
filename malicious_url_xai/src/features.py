"""Deterministic lexical feature extraction from URL strings (no network calls)."""
import ipaddress
import math
import re
from collections import Counter
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
WWW_RE = re.compile(r"^www\.", re.IGNORECASE)
PORT_RE = re.compile(r":\d+$")
PCT_RE = re.compile(r"%[0-9a-fA-F]{2}")

COUNTED_CHARS = {
    "count_dot": ".",
    "count_hyphen": "-",
    "count_underscore": "_",
    "count_slash": "/",
    "count_question": "?",
    "count_equal": "=",
    "count_at": "@",
    "count_amp": "&",
    "count_percent": "%",
}

FEATURE_NAMES = [
    "url_len", "host_len", "path_len", "query_len",
    *COUNTED_CHARS,
    "count_digits", "count_letters",
    "digit_ratio", "special_ratio",
    "subdomain_count", "path_depth", "query_param_count",
    "host_is_ip", "has_port", "has_pct_encoding",
    "entropy",
]
RAW_EXTRA_FEATURES = ["is_https", "has_scheme"]


def normalize_url(url: str) -> str:
    """Remove surrounding whitespace, the scheme and one leading 'www.'; keep everything else as-is."""
    url = SCHEME_RE.sub("", url.strip(), count=1)
    return WWW_RE.sub("", url, count=1)


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def _split(url: str):
    """Return (netloc, hostname, path, query); tolerant of malformed URLs."""
    target = url if SCHEME_RE.match(url) else "//" + url
    try:
        parts = urlsplit(target)
        netloc, path, query = parts.netloc, parts.path, parts.query
        host = parts.hostname or ""
    except ValueError:
        netloc = re.split(r"[/?#]", url.split("://", 1)[-1], maxsplit=1)[0]
        rest = url[url.find(netloc) + len(netloc):]
        path, _, query = rest.partition("?")
        host = netloc.rsplit("@", 1)[-1].split(":", 1)[0].lower()
    return netloc, host, path, query


def hostname(url: str) -> str:
    return _split(url)[1]


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def extract_features(url: str, raw: bool = False) -> list:
    """Feature vector in FEATURE_NAMES order (+ RAW_EXTRA_FEATURES when raw=True)."""
    netloc, host, path, query = _split(url)
    n = len(url)
    denom = max(n, 1)
    digits = sum(ch.isdigit() for ch in url)
    letters = sum(ch.isalpha() for ch in url)
    special = n - digits - letters
    is_ip = _is_ip(host)
    labels = [p for p in host.split(".") if p]

    row = [
        n, len(host), len(path), len(query),
        *(url.count(ch) for ch in COUNTED_CHARS.values()),
        digits, letters,
        digits / denom, special / denom,
        0 if is_ip else max(len(labels) - 2, 0),
        len([seg for seg in path.split("/") if seg]),
        len([p for p in query.split("&") if p]),
        int(is_ip),
        int(bool(PORT_RE.search(netloc))),
        int(bool(PCT_RE.search(url))),
        shannon_entropy(url),
    ]
    if raw:
        lowered = url.lower()
        row += [int(lowered.startswith("https://")), int(bool(SCHEME_RE.match(url)))]
    return row


def build_feature_frame(urls, raw: bool = False) -> pd.DataFrame:
    cols = FEATURE_NAMES + (RAW_EXTRA_FEATURES if raw else [])
    df = pd.DataFrame([extract_features(u, raw=raw) for u in urls], columns=cols, dtype=np.float64)
    assert np.isfinite(df.to_numpy()).all(), "feature matrix contains NaN or infinity"
    return df
