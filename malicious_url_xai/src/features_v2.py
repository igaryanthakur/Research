"""V2 lexical features: the 24 V1 features followed by 15 frozen additions (no network calls).

Input is the normalized URL (scheme and one leading 'www.' already removed). No scheme,
HTTP/HTTPS or 'www' indicator is produced, because those encode collection-source formatting.
"""
import re
from datetime import datetime
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

from src.features import FEATURE_NAMES, SCHEME_RE, _is_ip, _split, extract_features

FEATURE_VERSION = "v2.0"
NORMALIZATION_VERSION = "v1: strip whitespace, one leading scheme://, one leading www."

EXTRA_CHARS = {
    "count_colon": ":",
    "count_hash": "#",
    "count_plus": "+",
    "count_tilde": "~",
    "count_semicolon": ";",
}

STRUCTURAL_FEATURES = [
    *EXTRA_CHARS,
    "first_dir_len",
    "longest_path_segment_len",
    "tld_len",
    "host_label_count",
    "max_host_label_len",
    "fragment_len",
    "embedded_double_slash_count",
]
LEXICON_FEATURES = ["suspicious_token_count", "is_shortener_host", "has_punycode"]
FEATURE_NAMES_V2 = FEATURE_NAMES + STRUCTURAL_FEATURES + LEXICON_FEATURES

SUSPICIOUS_TOKENS = frozenset({
    "login", "signin", "logon", "verify", "verification", "secure", "account", "update",
    "confirm", "bank", "banking", "paypal", "password", "credential", "credentials", "bonus",
    "free", "service", "webscr", "ebayisapi", "wallet", "suspend",
})
SHORTENER_HOSTS = frozenset({
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly",
    "rebrand.ly", "tiny.cc", "bit.do", "shorturl.at", "rb.gy", "v.gd", "tr.im", "cli.gs",
    "x.co", "adf.ly", "bl.ink", "lnkd.in", "db.tt", "qr.ae", "po.st", "j.mp",
})
TOKEN_RE = re.compile(r"[a-z0-9]+")

FEATURE_DEFINITIONS = {
    **{name: f"count of literal '{ch}' in the normalized URL" for name, ch in EXTRA_CHARS.items()},
    "first_dir_len": "length of the first non-empty path segment; 0 when absent",
    "longest_path_segment_len": "maximum non-empty path-segment length; 0 when absent",
    "tld_len": "length of the final hostname label; 0 for IP or empty hosts",
    "host_label_count": "number of non-empty hostname labels; 0 for IP or empty hosts",
    "max_host_label_len": "maximum hostname-label length; 0 for IP or empty hosts",
    "fragment_len": "length of the URL fragment after '#'",
    "embedded_double_slash_count": "non-overlapping '//' occurrences in path, query and fragment",
    "suspicious_token_count": "number of [a-z0-9]+ tokens of the lowercased URL that exactly match SUSPICIOUS_TOKENS",
    "is_shortener_host": "1 if the hostname (trailing dot removed) exactly matches SHORTENER_HOSTS",
    "has_punycode": "1 if any hostname label starts with 'xn--'",
}


def _fragment(url: str) -> str:
    target = url if SCHEME_RE.match(url) else "//" + url
    try:
        return urlsplit(target).fragment
    except ValueError:
        return url.partition("#")[2]


def extract_features_v2(url: str) -> list:
    """Feature vector in FEATURE_NAMES_V2 order."""
    _, host, path, query = _split(url)
    fragment = _fragment(url)
    segments = [seg for seg in path.split("/") if seg]
    host = host.rstrip(".")
    is_ip = _is_ip(host)
    labels = [] if is_ip else [p for p in host.split(".") if p]

    row = extract_features(url)
    row += [
        *(url.count(ch) for ch in EXTRA_CHARS.values()),
        len(segments[0]) if segments else 0,
        max(map(len, segments), default=0),
        len(labels[-1]) if labels else 0,
        len(labels),
        max(map(len, labels), default=0),
        len(fragment),
        path.count("//") + query.count("//") + fragment.count("//"),
        sum(tok in SUSPICIOUS_TOKENS for tok in TOKEN_RE.findall(url.lower())),
        int(host in SHORTENER_HOSTS),
        int(any(label.startswith("xn--") for label in labels)),
    ]
    assert len(row) == len(FEATURE_NAMES_V2)
    return row


def build_feature_frame_v2(urls, index=None) -> pd.DataFrame:
    df = pd.DataFrame([extract_features_v2(u) for u in urls], columns=FEATURE_NAMES_V2,
                      index=index, dtype=np.float64)
    assert list(df.columns) == FEATURE_NAMES_V2
    assert np.isfinite(df.to_numpy()).all(), "feature matrix contains NaN or infinity"
    return df


def feature_manifest(dropped=None) -> dict:
    dropped = dropped or {}
    return {
        "feature_version": FEATURE_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "feature_names": FEATURE_NAMES_V2,
        "blocks": {"v1": FEATURE_NAMES, "structural": STRUCTURAL_FEATURES,
                   "lexicon": LEXICON_FEATURES},
        "definitions_new": FEATURE_DEFINITIONS,
        "suspicious_tokens": sorted(SUSPICIOUS_TOKENS),
        "shortener_hosts": sorted(SHORTENER_HOSTS),
        "dropped_features": dropped,
    }
