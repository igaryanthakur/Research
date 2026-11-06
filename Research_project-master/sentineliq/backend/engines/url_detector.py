"""
engines/url_detector.py — Enterprise 3-Tier URL/Phishing Orchestrator
================================================================

Architecture (Enterprise Pipeline):
  1. Apex Domain Normalization (tldextract)
  2. Redirect Unwinding (handles wrappers/shorteners)
  3. Tier 1: Reputation Fast Pass (Tranco Top 10k cache + Exceptions)
  4. Tier 2: Standard Analysis (WHOIS + Rules + BERT Model)
  5. Tier 3: Deep Inspection (DOM scraping) on escalation
  6. Graceful degradation across all layers.
"""

import os
import re
import asyncio
import logging
import math
import concurrent.futures
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    import tldextract  # type: ignore[import]
    _TLDEXTRACT_AVAILABLE = True
except ImportError:
    _TLDEXTRACT_AVAILABLE = False
    logger = logging.getLogger("sentineliq.url")
    logger.warning("tldextract not installed — Apex Domain Normalization degraded.")

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

logger = logging.getLogger("sentineliq.url")

from config import URLConfig, APIConfig, HOMOGLYPH_MAP  # type: ignore[import]
from engines.reputation_cache import TrancoCache  # type: ignore[import]
from engines.redirect_unwinder import RedirectUnwinder  # type: ignore[import]

# ─── Module-load compiled patterns (never recompile per-request) ──────────────
# GENERIC_URL_PATTERNS compiled once here; _rule_based_features uses this list.
_COMPILED_GENERIC_URL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in URLConfig.GENERIC_URL_PATTERNS
]

# ─── Bounded ThreadPoolExecutor for WHOIS I/O ─────────────────────────────────
# threading.Thread is prohibited in async FastAPI context for IO-bound tasks.
# Max workers capped by URLConfig.WHOIS_MAX_WORKERS (default 4).
_WHOIS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=URLConfig.WHOIS_MAX_WORKERS,
    thread_name_prefix="whois_worker"
)

# Lazy optional imports
try:
    from bs4 import BeautifulSoup  # type: ignore[import]
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False
    logger.warning("BeautifulSoup not installed — Tier 3 DOM scraping disabled.")

try:
    import httpx  # type: ignore[import]
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    logger.warning("httpx not installed — Tier 3 DOM scraping disabled.")

_MALICIOUS_LABELS = {"label_1", "phishing", "malicious", "unsafe", "1"}
_SAFE_LABELS      = {"label_0", "safe", "benign", "0"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_private_host(hostname: str) -> bool:
    return any(hostname.startswith(p) for p in URLConfig.PRIVATE_IP_PREFIXES) or not hostname

def _normalize_hostname_for_brand(hostname: str) -> str:
    """Apply HOMOGLYPH_MAP to hostname for brand spoof detection.
    Catches amaz0n→amazon, paypa1→paypal, g00gle→google, rnicrosoft→microsoft.
    Only used for brand comparison — never mutates the actual hostname."""
    h = hostname.lower()
    for fake, real in HOMOGLYPH_MAP.items():
        h = h.replace(fake, real.lower() if real else "")
    # Digit-substitution normalization for brand spoofing
    for digit, letter in (("0", "o"), ("1", "l"), ("3", "e"), ("4", "a"), ("5", "s"), ("@", "a")):
        h = h.replace(digit, letter)
    return h


def _is_brand_spoof(hostname: str, apex_domain: str) -> bool:
    import difflib
    h_raw = hostname.lower()
    apex = apex_domain.lower() if apex_domain else h_raw
    apex_norm = _normalize_hostname_for_brand(apex)
    apex_name = apex_norm.split('.')[0] if '.' in apex_norm else apex_norm

    for brand in URLConfig.BRAND_NAMES:
        canonicals = URLConfig.BRAND_CANONICAL.get(brand, (f"{brand}.com",))
        canonical_match = any(
            h_raw == c.lstrip(".") or h_raw.endswith("." + c.lstrip("."))
            for c in canonicals
        )
        if canonical_match:
            continue  # Legitimate domain for this brand, check other brands just in case

        brand_lower = brand.lower()
        
        # Exact match on apex name
        if apex_name == brand_lower:
            return True
            
        # Fuzzy match (e.g. paypa1 vs paypal)
        ratio = difflib.SequenceMatcher(None, apex_name, brand_lower).ratio()
        if ratio > 0.85:
            return True

    return False

# ─── WHOIS domain age (with Graceful Degradation) ─────────────────────────────

def _check_domain_age(hostname: str) -> Dict[str, Any]:
    """WHOIS domain age check via bounded ThreadPoolExecutor.
    threading.Thread is prohibited in async FastAPI context — use _WHOIS_EXECUTOR."""
    if not hostname or _is_private_host(hostname):
        return {"age_days": None, "new_domain": False, "very_new_domain": False}
    try:
        import whois  # type: ignore[import]
        import io
        import contextlib
        from datetime import datetime, timezone

        result_holder: Dict[str, Any] = {}

        def _do_whois() -> None:
            f = io.StringIO()
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                try:
                    w = whois.whois(hostname)
                    result_holder["w"] = w
                except Exception as exc:
                    result_holder["err"] = exc

        # Submit to bounded executor — never use threading.Thread directly
        future = _WHOIS_EXECUTOR.submit(_do_whois)
        try:
            future.result(timeout=URLConfig.WHOIS_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            logger.debug("WHOIS timeout for %s after %ds", hostname, URLConfig.WHOIS_TIMEOUT_SECONDS)

        if "err" in result_holder or "w" not in result_holder:
            return {"age_days": None, "new_domain": False, "very_new_domain": False}

        w = result_holder["w"]
        creation = w.creation_date

        if isinstance(creation, list):
            creation = creation[0] if creation else None
        if creation is None:
            return {"age_days": None, "new_domain": False, "very_new_domain": False}

        if hasattr(creation, "tzinfo") and creation.tzinfo is None:
            creation = creation.replace(tzinfo=timezone.utc)

        age_days = int((datetime.now(timezone.utc) - creation).days)
        return {
            "age_days":        age_days,
            "new_domain":      bool(age_days < URLConfig.WHOIS_NEW_DOMAIN_DAYS),
            "very_new_domain": bool(age_days < URLConfig.WHOIS_VERY_NEW_DOMAIN_DAYS),
        }
    except Exception as e:
        logger.debug("whois degradation for %s: %s", hostname, e)
        return {"age_days": None, "new_domain": False, "very_new_domain": False}

# ─── Rule engine ──────────────────────────────────────────────────────────────

def _rule_based_features(url: str, domain_age: Dict[str, Any], redirect_depth: int, apex_domain: str = "") -> Dict[str, float]:
    url_str = str(url)
    try:
        parsed = urlparse(url_str if "://" in url_str else f"http://{url_str}")
    except ValueError:
        return {k: 0.0 for k in URLConfig.RULE_WEIGHTS}

    hostname = str(parsed.hostname or "").lower()
    path = str(parsed.path).lower()
    query = str(parsed.query).lower()
    full_path_query = path + "?" + query if query else path

    has_ip = float(bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", hostname)))
    suspicious_tld = float(any(hostname.endswith(tld) for tld in URLConfig.SUSPICIOUS_TLDS))
    brand_spoof = float(_is_brand_spoof(hostname, apex_domain))
    suspicious_keywords = float(any(kw in full_path_query or kw in hostname for kw in URLConfig.SUSPICIOUS_KEYWORDS))

    no_https = float(str(parsed.scheme).lower() != "https" and not _is_private_host(hostname))
    excessive_subdomains = float(hostname.count(".") > URLConfig.EXCESSIVE_SUBDOMAIN_DOTS)
    url_too_long = float(len(url_str) > URLConfig.MAX_URL_LENGTH)
    has_at_symbol = float("@" in url_str)
    at_routing = float("@" in path or ("@" in url_str and "@" not in hostname))
    new_domain = float(domain_age.get("new_domain", False))
    very_new_domain = float(domain_age.get("very_new_domain", False))

    # Keyword stacking: scan FULL URL string (hostname + subdomain + path + query)
    # Spec: must not scan only path/query — hostname abuse patterns must be caught.
    full_url_lower = url_str.lower()
    pair_hits = sum(
        1 for (w1, w2) in URLConfig.PHISHING_KEYWORD_PAIRS
        if w1 in full_url_lower and w2 in full_url_lower
    )
    keyword_stacking = float(min(1.0, pair_hits * 0.3)) if pair_hits >= 2 else 0.0

    # Redirection Depth Signal
    redirect_risk = min(1.0, redirect_depth * 0.25)

    # Generic URL structural patterns — evaluated from _COMPILED_GENERIC_URL_PATTERNS
    # compiled once at module load. Indices match URLConfig.GENERIC_URL_PATTERNS order.
    return {
        "has_ip":               has_ip,
        "suspicious_tld":       suspicious_tld,
        "brand_spoof":          brand_spoof,
        "suspicious_keywords":  suspicious_keywords,
        "no_https":             no_https,
        "excessive_subdomains": excessive_subdomains,
        "url_too_long":         url_too_long,
        "has_at_symbol":        has_at_symbol,
        "at_routing":           at_routing,
        "new_domain":           new_domain,
        "very_new_domain":      very_new_domain,
        "keyword_stacking":     keyword_stacking,
        "deceptive_subdomain":      float(bool(_COMPILED_GENERIC_URL_PATTERNS[0].search(url_str))),
        "path_keyword_stacking":    float(bool(_COMPILED_GENERIC_URL_PATTERNS[1].search(url_str))),
        "redirect_chain_keyword":   float(bool(_COMPILED_GENERIC_URL_PATTERNS[2].search(url_str))),
        "numeric_subdomain":        float(bool(_COMPILED_GENERIC_URL_PATTERNS[3].search(url_str))),
        "generic_abuse_keywords":   float(bool(_COMPILED_GENERIC_URL_PATTERNS[4].search(url_str))),
        "redirect_obfuscation":     redirect_risk,
    }


def _weighted_rule_score(features: Dict[str, float]) -> float:
    """Compute weighted rule score.

    Key invariants (per spec):
    - redirect_obfuscation is in URLConfig.RULE_WEIGHTS — processed uniformly,
      never manually added to both numerator and denominator separately.
    - The 1.4x compound multiplier applies to raw score BEFORE boost is added.
    - All signal weights come exclusively from URLConfig.RULE_WEIGHTS.
    """
    fired_items = [(k, v) for k, v in features.items() if v > 0]
    if not fired_items:
        return 0.0

    # All weights from config — redirect_obfuscation included uniformly
    total_weight = sum(URLConfig.RULE_WEIGHTS.get(k, 0.5) for k in features)
    fired_weight = sum(URLConfig.RULE_WEIGHTS.get(k, 0.5) * v for k, v in features.items())
    raw = fired_weight / total_weight if total_weight > 0 else 0.0

    # Compound signal multiplier: 1.4x on raw score BEFORE adding boost
    if len(fired_items) >= 3:
        raw = raw * 1.4

    # Multi-signal boost for heavy signals (weight >= HIGH_WEIGHT_SIGNAL_THRESHOLD)
    heavy_fired = sum(
        1 for k, v in features.items()
        if v > 0 and URLConfig.RULE_WEIGHTS.get(k, 0.0) >= URLConfig.HIGH_WEIGHT_SIGNAL_THRESHOLD
    )
    boost = min(URLConfig.MULTI_SIGNAL_BOOST_CAP, heavy_fired * URLConfig.MULTI_SIGNAL_BOOST_PER_HIT)

    return min(1.0, raw + boost)

def _features_to_shap(features: Dict[str, float]) -> List[Dict[str, Any]]:
    shap = []
    for name, val in features.items():
        if val > 0:
            if "Safe Browsing API" in name or "Threat Intelligence Feed" in name:
                w = val
            else:
                # redirect_obfuscation is in RULE_WEIGHTS at 0.85 — no special-case needed.
                # The special-case 'if name != redirect_obfuscation else 0.85' was redundant
                # and a maintenance hazard (would silently drift if the weight changed).
                w = URLConfig.RULE_WEIGHTS.get(name, 0.5) * val
            shap.append({
                "feature":   name.replace("_", " "),
                "weight":    float(int(float(w) * 10000)) / 10000.0,
                "direction": "positive",
            })
    return sorted(shap, key=lambda x: float(x["weight"]), reverse=True)


# ─── Model inference ──────────────────────────────────────────────────────────

def _model_confidence(model: Any, url_str: str) -> float:
    try:
        if not model:
            return 0.0
        _url = str(url_str)
        _url = _url[:512] if len(_url) > 512 else _url
        raw = model(_url) if callable(model) else []
        result: Dict[str, Any] = raw[0] if isinstance(raw, list) and len(raw) > 0 else raw if isinstance(raw, dict) else {}
        lbl = str(result.get("label", "")).lower().strip()
        sc = float(result.get("score", 0.5))

        if lbl in _MALICIOUS_LABELS:
            return sc
        elif lbl in _SAFE_LABELS:
            return 1.0 - sc
        return 0.5
    except Exception as infer_exc:
        logger.warning(f"BERT model graceful degradation: {infer_exc}")
        return 0.0

# ─── Tier 3: DOM scraping (Deep Inspection) ───────────────────────────────────

async def _fetch_and_analyze_dom(url: str, hostname: str) -> Dict[str, Any]:
    if not _BS4_AVAILABLE or not _HTTPX_AVAILABLE:
        return {}
    try:
        async with httpx.AsyncClient(timeout=URLConfig.DOM_FETCH_TIMEOUT, verify=URLConfig.DOM_VERIFY_SSL, follow_redirects=True) as client:  # type: ignore
            resp = await client.get(url)
            if resp.status_code != 200:
                return {}

            soup = BeautifulSoup(resp.text, "html.parser") # type: ignore
            title_node = soup.title
            title = str(title_node.string).lower() if (title_node and title_node.string) else ""
            has_password = bool(soup.find("input", {"type": "password"}))

            spoofed_brand = None
            for brand in URLConfig.BRAND_NAMES:
                if brand in str(title):
                    spoofed_brand = brand
                    break

            if spoofed_brand and has_password:
                return {"is_zero_day_phishing": True, "reason": f"Page claims to be '{spoofed_brand}' and asks for password on '{hostname}'."}
            return {}
    except Exception as exc:
        logger.debug(f"Tier 3 DOM degradation: {exc}")
    return {}

# ─── Live Threat Intelligence Feeds ───────────────────────────────────────────

async def _check_live_threat_feeds(url: str) -> Dict[str, Any]:
    """Check open threat intelligence feeds (URLhaus + GSB API) concurrently."""
    if not _HTTPX_AVAILABLE:
        return {}

    async def check_urlhaus() -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=APIConfig.URLHAUS_TIMEOUT) as client: # type: ignore
                resp = await client.post(APIConfig.URLHAUS_API_URL, data={"url": url})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("query_status") == "ok" and data.get("url_status") == "online":
                        return {"source": "URLhaus Threat Intelligence Feed", "is_malicious": True, "score_boost": 0.50}
        except Exception as exc:
            logger.debug(f"URLhaus API Timeout/Error: {exc}")
        return {}

    async def check_gsb() -> Dict[str, Any]:
        if not APIConfig.SAFE_BROWSING_API_KEY:
            return {"api_failed": True, "penalty": APIConfig.SAFE_BROWSING_FALLBACK_PENALTY}
        try:
            payload = {
                "client": {"clientId": "sentineliq", "clientVersion": "1.0.0"},
                "threatInfo": {
                    "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": url}]
                }
            }
            logger.info(f"Querying Google Safe Browsing API for {url}")
            async with httpx.AsyncClient(timeout=APIConfig.SAFE_BROWSING_TIMEOUT) as client: # type: ignore
                resp = await client.post(
                    f"{APIConfig.SAFE_BROWSING_API_URL}?key={APIConfig.SAFE_BROWSING_API_KEY}", 
                    json=payload
                )
                logger.info(f"Google Safe Browsing API returned status {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    if "matches" in data and len(data["matches"]) > 0:
                        return {"source": "Google Safe Browsing API", "is_malicious": True, "score_boost": 0.95}
                elif resp.status_code == 429:
                    logger.warning(f"Safe Browsing Rate Limit Hit! Fallback: {APIConfig.SAFE_BROWSING_FALLBACK_BEHAVIOR}")
                    return {"api_failed": True, "penalty": APIConfig.SAFE_BROWSING_FALLBACK_PENALTY}
        except Exception as exc:
            logger.debug(f"Safe Browsing API Timeout/Error: {exc}")
            return {"api_failed": True, "penalty": APIConfig.SAFE_BROWSING_FALLBACK_PENALTY}
        return {}

    results = await asyncio.gather(check_urlhaus(), check_gsb(), return_exceptions=True)

    # Log any exceptions from gather before discarding — distinguishes "API returned
    # empty" from "API threw an exception" which are different failure modes.
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            feed_name = ["URLhaus", "SafeBrowsing"][i]
            logger.warning("[ThreatFeed] %s raised exception (non-fatal): %s", feed_name, res)

    urlhaus_res = results[0] if isinstance(results[0], dict) else {}
    gsb_res     = results[1] if isinstance(results[1], dict) else {}

    # Prioritize GSB hit over URLhaus if both fire
    if gsb_res.get("is_malicious"):
        return gsb_res
    if urlhaus_res.get("is_malicious"):
        return urlhaus_res
    
    if gsb_res.get("api_failed"):
        return gsb_res

    return {}

# ─── Orchestrator Initialization ──────────────────────────────────────────────

async def load_url_model(app: Any) -> None:
    is_serverless = os.getenv("VERCEL") == "1" or os.getenv("RENDER") == "true" or os.getenv("LIGHTWEIGHT_MODE", "false").lower() == "true"
    
    # Pre-warm the Tranco cache
    await TrancoCache.initialize()
    
    if is_serverless:
        app.state.url_model = None
        app.state.url_mode = "rule_based_fallback (lightweight mode)"
        logger.info("Serverless Mode: Skipping BERT.")
        return

    cache_dir = os.getenv("MODEL_CACHE_DIR", "./model_cache")
    os.makedirs(cache_dir, exist_ok=True)
    try:
        loop = asyncio.get_running_loop()
        def _load() -> Any:
            from transformers import pipeline  # type: ignore[import]
            return pipeline("text-classification", model=URLConfig.MODEL_NAME, tokenizer=URLConfig.MODEL_NAME, model_kwargs={"cache_dir": cache_dir}, truncation=True, max_length=512, device=-1)

        pipe = await loop.run_in_executor(None, _load)
        app.state.url_model = pipe
        app.state.url_mode = "distilbert_model"
        logger.info(f"URL BERT model loaded: {URLConfig.MODEL_NAME}")
    except Exception as exc:
        app.state.url_model = None
        app.state.url_mode = "rule_based_fallback"
        logger.warning(f"BERT model load degraded to rules: {exc}")


# ─── Enterprise Pipeline Orchestrator ─────────────────────────────────────────

async def detect_url(url: str, app_state: Any) -> Dict[str, Any]:
    """
    Enterprise 3-Tier Pipeline
    1. Unwind
    2. Apex Normalization
    3. Tier 1 (Fast Pass) OR Tier 2 (Standard Analysis)
    4. Tier 3 (Escalation)
    """
    try:
        url_str = str(url).strip()
        
        # Guard: Local/Private IP Fast Path
        try:
            p = urlparse(url_str if "://" in url_str else f"http://{url_str}")
        except ValueError:
            p = urlparse("http://invalid")
        if _is_private_host(str(p.hostname or "").lower()):
            return {
                "confidence": 0.0, "verdict": "BENIGN", "shap_features": [],
                "mode": "private_ip_fast_path", "domain_age_days": None, "redirect_depth": 0, "tier_used": "Tier 0"
            }

        # Step 1: Redirect Unwinding
        unwind_res = await RedirectUnwinder.unwind(url_str)
        final_url = unwind_res["final_url"]
        redirect_depth = unwind_res["redirect_depth"]
        wrappers = unwind_res["wrappers"]
        
        # Step 2: Apex Domain Normalization
        if _TLDEXTRACT_AVAILABLE:
            extracted = tldextract.extract(final_url) # type: ignore
            apex_domain = f"{extracted.domain}.{extracted.suffix}" if extracted.domain and extracted.suffix else str(urlparse(final_url).hostname)
        else:
            # Fallback to naive hostname if tldextract is unavailable
            apex_domain = str(urlparse(final_url).hostname or "").lower()
            
        hostname = str(urlparse(final_url).hostname or "").lower()

        loop = asyncio.get_running_loop()
        
        # Step 3: Tier 1 Reputation Fast Pass (Conditional)
        is_tier_1 = TrancoCache.is_tier_1_reputation(apex_domain) and redirect_depth == 0
        if is_tier_1:
            # Run lightweight rules. Bypass expensive WHOIS/BERT only if rules are clean.
            dummy_age = {"age_days": None, "new_domain": False, "very_new_domain": False}
            t1_rules = _rule_based_features(final_url, dummy_age, redirect_depth, apex_domain)
            t1_score = _weighted_rule_score(t1_rules)
            
            if t1_score < URLConfig.SUSPICIOUS_THRESHOLD:
                return {
                    "confidence": max(0.05, t1_score),
                    "verdict": "BENIGN",
                    "shap_features": [{"feature": "Tier 1 Tranco Trusted", "weight": 1.0, "direction": "negative"}],
                    "mode": "tier_1_fast_pass",
                    "domain_age_days": None,
                    "redirect_depth": redirect_depth,
                    "tier_used": "Tier 1"
                }
            # If t1_score is suspicious, fall through to full Tier 2 analysis

        # Step 3.5: Live Threat Intelligence Feeds (Tier 1.5)
        threat_feed = await _check_live_threat_feeds(final_url)
        has_live_hit = threat_feed.get("is_malicious", False)

        # Step 4: Tier 2 Standard Analysis
        domain_age = await loop.run_in_executor(None, _check_domain_age, hostname)
        rule_features = _rule_based_features(final_url, domain_age, redirect_depth, apex_domain)
        
        # If we got a live hit, we still want to calculate rule features (like Brand Spoof) for corroboration.
        # We manually inject the threat feed hit into the features map.
        if has_live_hit:
            rule_features[threat_feed["source"]] = threat_feed.get("score_boost", 0.90)

        shap_features = _features_to_shap(rule_features)
        
        # Explicitly ensure the active attack signal gets the right category
        for f in shap_features:
            if "Threat Intelligence Feed" in f["feature"] or "Safe Browsing API" in f["feature"]:
                f["category"] = "active_attack_signal"
                
        rule_score = _weighted_rule_score(rule_features)

        model = getattr(app_state, "url_model", None)
        mode = "tier_2_standard"

        model_conf = 0.0
        if model is not None:
            def _infer() -> float:
                return _model_confidence(model, final_url)
            model_conf = await loop.run_in_executor(None, _infer)

        if model is None:
            final_conf = float(int(rule_score * 10000)) / 10000.0
        else:
            w_score = URLConfig.BERT_WEIGHT * model_conf + URLConfig.RULE_WEIGHT * rule_score
            final_conf = float(int(w_score * 10000)) / 10000.0

        # Calibration removed: The Platt scale prior inverted the trust model
        # Score starts at zero. Confidence is earned, not assumed.
            
        # Apply API Fallback Penalty if Live Threat feeds failed (reduces certainty)
        if threat_feed.get("api_failed", False):
            penalty = float(threat_feed.get("penalty", 0.0))
            if final_conf > URLConfig.SUSPICIOUS_THRESHOLD:
                final_conf -= penalty

        # Signal Override Rule
        # If any single signal fires at or above URLConfig.SIGNAL_OVERRIDE_THRESHOLD:
        # - With corroboration (2+ signals total), forces MALICIOUS.
        # - Without corroboration, forces SUSPICIOUS (avoids single-signal false positives).
        # Threshold lives in URLConfig — not hardcoded here.
        highest_signal = max((float(feat["weight"]) for feat in shap_features), default=0.0)
        if highest_signal >= URLConfig.SIGNAL_OVERRIDE_THRESHOLD:
            if len(shap_features) >= 2:
                final_conf = max(final_conf, URLConfig.MALICIOUS_THRESHOLD + 0.05)
            else:
                final_conf = max(final_conf, URLConfig.SUSPICIOUS_THRESHOLD + 0.05)

        final_conf = min(1.0, max(0.0, final_conf))

        verdict = (
            "MALICIOUS"   if final_conf >= URLConfig.MALICIOUS_THRESHOLD
            else "SUSPICIOUS" if final_conf >= URLConfig.SUSPICIOUS_THRESHOLD
            else "BENIGN"
        )
        tier_used = "Tier 2"

        # Step 5: Tier 3 Escalation (Deep Inspection)
        if final_conf >= URLConfig.SUSPICIOUS_THRESHOLD:
            tier_used = "Tier 3"
            mode = "tier_3_deep_inspection"
            dom_analysis = await _fetch_and_analyze_dom(final_url, hostname)
            if dom_analysis.get("is_zero_day_phishing"):
                verdict = "MALICIOUS"
                final_conf = max(final_conf, 0.99)
                shap_features.insert(0, {"feature": "zero day dom spoof", "weight": 1.0, "direction": "positive"})

        if wrappers:
            shap_features.insert(0, {"feature": f"Redirect wrappers used: {','.join(wrappers)}", "weight": redirect_depth * 0.25, "direction": "positive"})

        return {
            "confidence": final_conf,
            "verdict": verdict,
            "shap_features": shap_features,
            "mode": mode,
            "domain_age_days": domain_age.get("age_days"),
            "redirect_depth": redirect_depth,
            "tier_used": tier_used
        }

    except Exception as exc:
        logger.error(f"Orchestrator unhandled error (Degraded to Safe): {exc}", exc_info=True)
        return {
            "confidence": 0.0,
            "verdict": "ERROR",
            "shap_features": [],
            "mode": "error_fallback",
            "domain_age_days": None,
            "redirect_depth": 0,
            "tier_used": "Error"
        }
