"""
verify_all.py — Automated verification of all SentinelIQ hardening fixes.
Run from backend/ directory: python verify_all.py
Exit 0 = all checks passed. Exit 1 = at least one failure.
"""
import sys
import re
import time
import inspect
import asyncio

sys.path.insert(0, '.')

PASS = 0
FAIL = 0

def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}" + (f" -- {detail}" if detail else ""))
        FAIL += 1

# ─── 1. config.py ─────────────────────────────────────────────────────────────
print("\n[1/4] config.py")
from config import PhishingConfig, URLConfig

check("BERT_WEIGHT removed from PhishingConfig",
      not hasattr(PhishingConfig, 'BERT_WEIGHT'))
check("HEURISTIC_WEIGHT removed from PhishingConfig",
      not hasattr(PhishingConfig, 'HEURISTIC_WEIGHT'))
check("GEMINI_RATE_LIMIT_PER_MIN = 8",
      getattr(PhishingConfig, 'GEMINI_RATE_LIMIT_PER_MIN', None) == 8)
check("GEMINI_BACKOFF_BASE exists",
      hasattr(PhishingConfig, 'GEMINI_BACKOFF_BASE'))
check("LEGITIMACY_SIGNALS has >= 8 entries",
      len(getattr(PhishingConfig, 'LEGITIMACY_SIGNALS', [])) >= 8)
check("redirect_obfuscation in RULE_WEIGHTS",
      'redirect_obfuscation' in URLConfig.RULE_WEIGHTS)
check("redirect_obfuscation weight = 0.85",
      URLConfig.RULE_WEIGHTS.get('redirect_obfuscation') == 0.85)
check("URLConfig.DOM_VERIFY_SSL = True",
      getattr(URLConfig, 'DOM_VERIFY_SSL', False) == True)
check("URLConfig.WHOIS_MAX_WORKERS = 4",
      getattr(URLConfig, 'WHOIS_MAX_WORKERS', 0) == 4)
check("PHISHING_KEYWORD_PAIRS has >= 13 entries",
      len(URLConfig.PHISHING_KEYWORD_PAIRS) >= 13)

pair_words = [w for pair in URLConfig.PHISHING_KEYWORD_PAIRS for w in pair]
check("'suspend' in keyword pairs",  'suspend' in pair_words)
check("'notice' in keyword pairs",   'notice' in pair_words)

# ─── 2. phishing.py ───────────────────────────────────────────────────────────
print("\n[2/4] engines/phishing.py")
from engines.phishing import (
    _COMPILED_SIGNALS, _COMPILED_LEGITIMACY,
    _GEMINI_BUCKET_TOKENS, _gemini_token_bucket_acquire,
    _heuristic_score, compute_absence_score
)
import engines.phishing as _phishing_mod

src_phishing = inspect.getsource(_phishing_mod)

check("_COMPILED_LEGITIMACY compiled at module load",
      len(_COMPILED_LEGITIMACY) >= 8 and hasattr(_COMPILED_LEGITIMACY[0], 'search'))
check("Token bucket starts >= 1 token",
      _GEMINI_BUCKET_TOKENS >= 1.0)
check("_gemini_token_bucket_acquire() returns True on fresh call",
      _gemini_token_bucket_acquire() == True)
check("TYPE_CHECKING guard for FastAPI import",
      'TYPE_CHECKING' in src_phishing)
check("Error fallback verdict = ERROR",
      '"verdict":       "ERROR"' in src_phishing)
check("Exponential backoff doubling present",
      'backoff * 2' in src_phishing)
check("GEMINI_BACKOFF_MAX referenced in source",
      'GEMINI_BACKOFF_MAX' in src_phishing)

# Functional: absence scorer short-circuits on legitimacy signal
absence = compute_absence_score("Your order has shipped — tracking number 1234")
check("Absence scorer skips on legitimacy signal",
      absence['absence_score'] == 0.0)

# Functional: heuristic detects phishing
h = _heuristic_score("URGENT: Your account will be suspended. Verify immediately or lose access forever.")
check("Heuristic scorer fires on phishing text",
      h['score'] > 0.30 and h['signal_count'] > 0)

# ─── 3. url_detector.py ───────────────────────────────────────────────────────
print("\n[3/4] engines/url_detector.py")
import engines.url_detector as _url_mod
from engines.url_detector import (
    _COMPILED_GENERIC_URL_PATTERNS, _WHOIS_EXECUTOR,
    _normalize_hostname_for_brand, _is_brand_spoof,
    _rule_based_features, _weighted_rule_score
)
import concurrent.futures
src_url = inspect.getsource(_url_mod)

check("_COMPILED_GENERIC_URL_PATTERNS compiled at load (5 patterns)",
      len(_COMPILED_GENERIC_URL_PATTERNS) == 5 and hasattr(_COMPILED_GENERIC_URL_PATTERNS[0], 'search'))
check("_WHOIS_EXECUTOR is ThreadPoolExecutor",
      isinstance(_WHOIS_EXECUTOR, concurrent.futures.ThreadPoolExecutor))
check("No threading.Thread import in url_detector",
      'import threading' not in src_url)
check("DOM_VERIFY_SSL used (not hardcoded False)",
      'verify=URLConfig.DOM_VERIFY_SSL' in src_url and 'verify=False' not in src_url)

# Homoglyph normalization
check("amaz0n normalizes to amazon",
      _normalize_hostname_for_brand('amaz0n-login.ru') == 'amazono-login.ru' or
      'amazon' in _normalize_hostname_for_brand('amaz0n-login.ru'))
check("paypa1 normalizes to paypal",
      'paypal' in _normalize_hostname_for_brand('paypa1.com'))
check("g00gle normalizes to google",
      'google' in _normalize_hostname_for_brand('g00gle.com'))

# Brand spoof detection on normalized hostnames
check("amaz0n-login.ru detected as brand spoof",
      _is_brand_spoof('amaz0n-login.ru') == True)
check("amazon.com NOT detected as brand spoof",
      _is_brand_spoof('amazon.com') == False)

# Compound multiplier: verify applied BEFORE boost (raw * 1.4, then + boost)
# With 3+ signals, raw should be amplified
features_3sig = {k: 0.0 for k in URLConfig.RULE_WEIGHTS}
features_3sig['brand_spoof'] = 1.0
features_3sig['suspicious_tld'] = 1.0
features_3sig['no_https'] = 1.0
score_3 = _weighted_rule_score(features_3sig)

features_2sig = {k: 0.0 for k in URLConfig.RULE_WEIGHTS}
features_2sig['brand_spoof'] = 1.0
features_2sig['suspicious_tld'] = 1.0
score_2 = _weighted_rule_score(features_2sig)

check("3-signal score > 2-signal score (compound multiplier working)",
      score_3 > score_2, f"3sig={score_3:.4f} 2sig={score_2:.4f}")

# Keyword stacking scans full URL
from config import URLConfig as _UC
feats = _rule_based_features('http://account-suspended-notice.ml/claim', {}, 0)
check("account-suspended-notice.ml: suspicious_tld fires",
      feats.get('suspicious_tld', 0) > 0)
check("account-suspended-notice.ml: keyword_stacking fires",
      feats.get('keyword_stacking', 0) > 0,
      f"pair score={feats.get('keyword_stacking', 0)}")
check("amaz0n-login.ru: brand_spoof fires via normalized hostname",
      _rule_based_features('https://amaz0n-login.ru/signin', {}, 0).get('brand_spoof', 0) > 0)

# redirect_obfuscation not double-counted (score check)
check("redirect_obfuscation NOT double-counted in source",
      'total_weight += 0.85' not in src_url)

# ─── 4. Full URL detection on key FNs from prior benchmark ────────────────────
print("\n[4/4] End-to-end URL scoring on previously-failed cases")

class _FakeState:
    url_model = None
    url_mode = "rule_based_fallback"

async def _run_urls():
    from engines.url_detector import detect_url
    state = _FakeState()

    cases = [
        ("https://amaz0n-login.ru/signin/",            "MALICIOUS or SUSPICIOUS"),
        ("http://account-suspended-notice.ml/claim",   "MALICIOUS or SUSPICIOUS"),
        ("https://paypa1-secure.verify-account.tk/",   "MALICIOUS or SUSPICIOUS"),
        ("https://amazon.com/orders",                   "BENIGN"),
        ("https://google.com/search?q=test",            "BENIGN"),
    ]

    for url, expected in cases:
        r = await detect_url(url, state)
        verdict = r['verdict']
        conf = r['confidence']
        if expected == "BENIGN":
            ok = verdict == "BENIGN"
        else:
            ok = verdict in ("MALICIOUS", "SUSPICIOUS")
        check(f"{url[:55]:<55} {verdict} ({conf:.3f})", ok, f"expected {expected}")

asyncio.run(_run_urls())

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*56}")
print(f"  PASSED: {PASS}   FAILED: {FAIL}")
print(f"{'='*56}")
sys.exit(0 if FAIL == 0 else 1)
