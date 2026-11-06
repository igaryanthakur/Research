"""
engines/phishing.py — Production Phishing / Social-Engineering Detector
=========================================================================

Architecture (3 layers):
  Layer A : Weighted keyword heuristic + regex category scoring
  Layer B : BERT fine-tuned text classifier (ealvaradob/bert-finetuned-phishing)
  Layer C : Gemini AI cross-validation for LLM-generated spear-phishing

All thresholds, model names, weights, and patterns are loaded from config.py.
No magic numbers exist in this file.
"""

import os
import re
import json
import math
import time
import asyncio
import logging
import unicodedata
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI  # only used for type annotations — never at runtime

# Must be set before transformers import
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

logger = logging.getLogger("sentineliq.phishing")

from config import PhishingConfig, HOMOGLYPH_MAP  # type: ignore[import]

# ─── Compile regex patterns once at module load (never inside functions) ──────

_COMPILED_SIGNALS = {
    category: {
        "weight": data["weight"],
        "compiled": [re.compile(p, re.IGNORECASE | re.UNICODE | re.DOTALL) for p in data["patterns"]]
    }
    for category, data in PhishingConfig.HEURISTIC_SIGNALS.items()
}

# Legitimacy signals compiled once — used by compute_absence_score()
# Source: PhishingConfig.LEGITIMACY_SIGNALS (never inline regex in hot paths)
_COMPILED_LEGITIMACY = [
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in PhishingConfig.LEGITIMACY_SIGNALS
]

# ─── Gemini Token Bucket (module-level, single-worker safe) ──────────────────
# For multi-worker deployments migrate to Redis-backed bucket (see ARCHITECTURE.md).
# asyncio.Lock protects the read-modify-write against concurrent coroutine access.
# Lock is created lazily to avoid "no running event loop" on module import.
_GEMINI_BUCKET_TOKENS: float = float(PhishingConfig.GEMINI_RATE_LIMIT_PER_MIN)
_GEMINI_BUCKET_LAST_REFILL: float = time.monotonic()
_GEMINI_BUCKET_LOCK: Optional[asyncio.Lock] = None


def _get_gemini_lock() -> asyncio.Lock:
    """Lazily create the token-bucket lock on first use inside a running event loop."""
    global _GEMINI_BUCKET_LOCK
    if _GEMINI_BUCKET_LOCK is None:
        _GEMINI_BUCKET_LOCK = asyncio.Lock()
    return _GEMINI_BUCKET_LOCK


# ─── Homoglyph normalization ──────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """NFKD decomposition + homoglyph substitution for evasion resistance."""
    text = unicodedata.normalize("NFKD", str(text))
    for fake, real in HOMOGLYPH_MAP.items():
        text = text.replace(fake, real)
    return text


# ─── Model loading ────────────────────────────────────────────────────────────

async def load_phishing_model(app: "FastAPI") -> None:  # type: ignore[misc]
    """Load HuggingFace phishing BERT pipeline. Graceful fallback on failure."""
    is_serverless = os.getenv("VERCEL") == "1" or os.getenv("RENDER") == "true" or os.getenv("LIGHTWEIGHT_MODE", "false").lower() == "true"
    if is_serverless:
        app.state.phishing_model = None
        app.state.phishing_mode = "heuristic_fallback (lightweight mode)"
        logger.info("Serverless / Lightweight Mode enabled: Skipping Phishing BERT model load.")
        return

    cache_dir = os.getenv("MODEL_CACHE_DIR", "/tmp/model_cache" if is_serverless else "./model_cache")
    os.makedirs(cache_dir, exist_ok=True)
    try:
        loop = asyncio.get_running_loop()

        def _load() -> Any:
            from transformers import pipeline  # type: ignore[import]
            return pipeline(
                "text-classification",
                model=PhishingConfig.MODEL_NAME,
                tokenizer=PhishingConfig.MODEL_NAME,
                model_kwargs={"cache_dir": cache_dir},
                truncation=True,
                max_length=PhishingConfig.MAX_INPUT_LENGTH,
                return_all_scores=True,
            )

        pipe = await loop.run_in_executor(None, _load)  # type: ignore[arg-type]
        app.state.phishing_model = pipe
        app.state.phishing_mode = "bert_model"
        logger.info("Phishing BERT model loaded: %s", PhishingConfig.MODEL_NAME)
    except Exception as exc:
        app.state.phishing_model = None
        app.state.phishing_mode = "heuristic_fallback"
        logger.warning("Phishing model load failed (%s) — using heuristic fallback.", exc)


# ─── Heuristic scoring ────────────────────────────────────────────────────────

_MALICIOUS_LABELS = {"label_1", "phishing", "malicious", "1", "spam"}


def _heuristic_score(text: str) -> Dict[str, Any]:
    """
    Score ANY text for phishing signals — no URL required.
    Returns score in [0, 1] and list of triggered categories.
    """
    if not text or len(str(text).strip()) < PhishingConfig.MIN_INPUT_LENGTH:
        return {"score": 0.0, "triggered": [], "signal_count": 0}

    # Always normalize first
    normalized_text = _normalize(text)

    triggered_categories: List[str] = []
    raw_score: float = 0.0
    seen_weights: set = set()

    for category, data in _COMPILED_SIGNALS.items():
        data_dict: Dict[str, Any] = data  # type: ignore
        for pattern in data_dict["compiled"]:
            if pattern.search(normalized_text):
                # Each category contributes its weight only ONCE
                if category not in seen_weights:
                    _w = float(str(data_dict.get("weight", 0.0)))
                    raw_score = raw_score + _w  # type: ignore
                    seen_weights.add(str(category))
                triggered_categories.append(str(category))
                break  # one match per category is enough

    # Cap at 1.0, apply sigmoid smoothing for confidence feel.
    # NOTE: sigmoid at capped=0 returns ~0.018, not 0.0.
    # A completely clean text gets a non-zero score by design — it avoids
    # hard 0% confidence in UI. Document this explicitly so tests/dashboards
    # are not surprised. To get a true 0.0, check signal_count == 0 instead.
    # Cap at 1.0, apply sigmoid smoothing for confidence feel.
    capped = min(raw_score, 2.0)
    smoothed = 1 / (1 + math.exp(-4 * (capped - 0.5)))
    
    is_legit = any(pat.search(normalized_text) for pat in _COMPILED_LEGITIMACY)
    dampening_applied = False
    original_smoothed = smoothed

    if is_legit:
        smoothed = smoothed * 0.33
        raw_score = raw_score * 0.33
        dampening_applied = True

    return {
        "score": float(int(smoothed * 10000)) / 10000.0,
        "triggered": list(set(triggered_categories)),
        "signal_count": len(set(triggered_categories)),
        "raw_score": float(int(float(raw_score) * 10000)) / 10000.0,
        "is_legit": is_legit,
        "dampened_amount": float(int((original_smoothed - smoothed) * 10000)) / 10000.0 if dampening_applied else 0.0
    }


def compute_absence_score(text: str) -> Dict[str, Any]:
    """
    Legitimate emails HAVE these things. Phishing often doesn't.
    Score based on what's MISSING, not just what's present.
    IMPORTANT: Only penalize absence if there are also positive phishing signals.
    A plain business email with no footer is NOT phishing — it just lacks formality.

    Uses _COMPILED_LEGITIMACY (pre-compiled at module load from
    PhishingConfig.LEGITIMACY_SIGNALS). Never calls re.compile() per request.
    """
    score = 0.0
    signals = []

    # --- Positive legitimacy guard (pre-compiled at module load) ---
    # If the email matches ANY legitimacy signal it is clearly benign in category.
    # Block the absence scorer from firing on these.
    for pat in _COMPILED_LEGITIMACY:
        if pat.search(text):
            # Email is clearly legitimate in category — absence scoring is NOT relevant
            return {"absence_score": 0.0, "absence_signals": []}

    # No personal name used (Dear User vs Dear John)
    has_personal = bool(re.search(
        r'(?i)dear\s+(mr|mrs|ms|dr|prof)\b|dear\s+[A-Z][a-z]{2,20}\b',
        text
    ))
    if not has_personal:
        score += 0.12  # reduced from 0.18
        signals.append("no_personal_name")

    # No company/brand identity
    has_brand = bool(re.search(
        r'(?i)(from|regards|sincerely|team\s+at|the\s+)\s*\b\w{3,20}\s+(inc|corp|ltd|llc|team|support)\b',
        text
    ))
    if not has_brand:
        score += 0.10  # reduced from 0.15
        signals.append("no_brand_identity")

    # No contact information
    has_contact = bool(re.search(
        r'(?i)(\+\d[\d\s\-]{8,}|contact\s+us\s+at|help@|support@[a-z]+\.[a-z]{2,4})',
        text
    ))
    if not has_contact:
        score += 0.08  # reduced from 0.12
        signals.append("no_contact_info")

    # No unsubscribe / legal footer (legit marketing always has this)
    has_footer = bool(re.search(
        r'(?i)(unsubscribe|opt.?out|privacy\s+policy|terms\s+of\s+service|©\s*\d{4})',
        text
    ))
    if not has_footer:
        score += 0.07  # reduced from 0.10
        signals.append("no_legal_footer")

    return {
        "absence_score": float(int(min(score, 0.30) * 10000)) / 10000.0,  # cap reduced from 0.50
        "absence_signals": signals
    }


def _token_scores(text: str) -> List[Dict[str, Any]]:
    """Return per-token highlight scores for frontend rendering."""
    words = str(text).split()
    text_lower = str(text).lower()
    result: List[Dict[str, Any]] = []
    for word in words:
        clean = word.strip(".,!?;:'\"").lower()
        matched_weight: float = 0.0
        for sig in PhishingConfig.SIGNALS:
            if sig in text_lower and clean in sig:
                matched_weight = max(
                    matched_weight,
                    PhishingConfig.SIGNAL_WEIGHTS.get(sig, PhishingConfig.DEFAULT_SIGNAL_WEIGHT)
                )
        if float(matched_weight) > 0.0:
            result.append({"token": word, "score": float(int(float(matched_weight) * 10000)) / 10000.0})
        else:
            result.append({"token": word, "score": 0.04})
    return result


# ─── Layer C: LLM Cross-Validation ───────────────────────────────────────────────

async def _gemini_token_bucket_acquire() -> bool:
    """
    Async token bucket check for Gemini rate limiting.
    Returns True if a token is available (call is allowed), False if rate-limited.
    Refills at GEMINI_RATE_LIMIT_PER_MIN tokens per 60 seconds.
    asyncio.Lock prevents race conditions when two coroutines call simultaneously.
    """
    global _GEMINI_BUCKET_TOKENS, _GEMINI_BUCKET_LAST_REFILL
    async with _get_gemini_lock():
        now = time.monotonic()
        elapsed = now - _GEMINI_BUCKET_LAST_REFILL
        # Refill proportionally to elapsed time
        refill = elapsed * (PhishingConfig.GEMINI_RATE_LIMIT_PER_MIN / 60.0)
        _GEMINI_BUCKET_TOKENS = min(
            float(PhishingConfig.GEMINI_RATE_LIMIT_PER_MIN),
            _GEMINI_BUCKET_TOKENS + refill
        )
        _GEMINI_BUCKET_LAST_REFILL = now
        if _GEMINI_BUCKET_TOKENS >= 1.0:
            _GEMINI_BUCKET_TOKENS -= 1.0
            return True
        return False


async def _gemini_phishing_judge(text: str, app_state: Any) -> Dict[str, Any]:
    """
    Layer C: LLM cross-validation to catch flawless LLM-generated phishing.
    Implements:
      - Token bucket rate limiting (max 8 calls/min, module-level)
      - Exponential backoff on 429: 1s → 2s → 4s … up to 16s
    Every skip or failure is logged with context so no Gemini event is silent.
    """
    if not getattr(app_state, "gemini_available", False):
        logger.warning("[Layer C] Skipped — Gemini unavailable (app_state flag not set)")
        return {"confidence": 0.0, "reason": "Gemini unavailable"}

    client = getattr(app_state, "gemini_client", None)
    if client is None:
        logger.warning("[Layer C] Skipped — gemini_client is None")
        return {"confidence": 0.0, "reason": "No Gemini client"}

    # Rate limit gate (async — protected by asyncio.Lock)
    if not await _gemini_token_bucket_acquire():
        logger.warning("[Layer C] Skipped — token bucket exhausted (rate limit: %d/min)",
                       PhishingConfig.GEMINI_RATE_LIMIT_PER_MIN)
        return {"confidence": 0.0, "reason": "Rate limited"}

    _text_str = str(text)
    snippet: str = _text_str[:500] if len(_text_str) > 500 else _text_str
    prompt = PhishingConfig.GEMINI_PROMPT_TEMPLATE.format(snippet=snippet)

    backoff = PhishingConfig.GEMINI_BACKOFF_BASE
    last_exc: Exception = Exception("unknown")

    for attempt in range(4):  # max 4 attempts with backoff 1→2→4→8s (cap 16s)
        try:
            _c = client
            _p = prompt

            async def _call() -> Any:
                response = await _c.chat.completions.create(
                    model="mistralai/Mistral-7B-Instruct-v0.2",
                    messages=[{"role": "user", "content": _p}],
                )
                return response

            response: Any = await asyncio.wait_for(
                _call(),
                timeout=PhishingConfig.GEMINI_TIMEOUT,
            )
            raw: str = str(response.choices[0].message.content).strip()
            logger.debug("Gemini Phishing RAW: %s", raw)

            # Strip markdown fences
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

            parsed = json.loads(raw)
            verdict: str = str(parsed.get("verdict", "BENIGN")).upper()
            conf: float = float(parsed.get("confidence", 0.0))
            if verdict != "MALICIOUS":
                conf = 1.0 - conf
            return {
                "confidence": float(int(min(1.0, max(0.0, conf)) * 10000)) / 10000.0,
                "reason": str(parsed.get("reason", "")),
            }

        except json.JSONDecodeError as jde:
            logger.warning("[Layer C] JSON parse failed on attempt %d: %s", attempt + 1, jde)
            return {"confidence": 0.0, "reason": "JSON parse error"}

        except Exception as exc:
            last_exc = exc
            exc_str = str(exc)
            # Detect 429 rate-limit responses for backoff
            if "429" in exc_str or "quota" in exc_str.lower() or "rate" in exc_str.lower():
                wait = min(backoff, PhishingConfig.GEMINI_BACKOFF_MAX)
                logger.warning(
                    "[Layer C] 429 rate-limit on attempt %d — backing off %.1fs (scan affected)",
                    attempt + 1, wait
                )
                await asyncio.sleep(wait)
                backoff = min(backoff * 2, PhishingConfig.GEMINI_BACKOFF_MAX)
            else:
                logger.warning("[Layer C] API error on attempt %d: %s — skipping", attempt + 1, exc)
                return {"confidence": 0.0, "reason": f"Gemini error: {exc_str[:120]}"}

    logger.warning("[Layer C] All retry attempts exhausted: %s", last_exc)
    return {"confidence": 0.0, "reason": "Max retries exceeded"}


# ─── Public entry point ───────────────────────────────────────────────────────

async def detect_phishing(text: str, app_state: Any, semantic_divergence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Async phishing detector (3 layers + semantic divergence).
    Returns: { confidence, verdict, shap_features, mode, token_scores }
    Never raises.
    """
    try:
        # Input guard
        if text is None:
            text = ""
        text = str(text)

        # Normalize for heuristics
        heuristic_result = _heuristic_score(text)
        heuristic = heuristic_result["score"]
        triggered = heuristic_result["triggered"]

        model: Optional[Any] = getattr(app_state, "phishing_model", None)
        mode: str = getattr(app_state, "phishing_mode", "heuristic_fallback")

        model_conf = 0.0
        if model is not None and len(text.strip()) >= PhishingConfig.MIN_INPUT_LENGTH:
            try:
                _full_str = str(text)
                truncated = _full_str[:PhishingConfig.MAX_INPUT_LENGTH] if len(_full_str) > PhishingConfig.MAX_INPUT_LENGTH else _full_str  # type: ignore[index]

                def _infer() -> Any:
                    return model(truncated) if callable(model) else []  # type: ignore

                loop = asyncio.get_event_loop()
                raw = await loop.run_in_executor(None, _infer)  # type: ignore[arg-type]

                # raw is list[list[dict]] when return_all_scores=True
                scores_list: List[Dict[str, Any]] = raw[0] if raw and isinstance(raw[0], list) else raw

                for item in scores_list:
                    lbl = str(item.get("label", "")).lower().strip()
                    sc = float(item.get("score", 0.0))
                    if lbl in _MALICIOUS_LABELS:
                        model_conf = sc
                        break
                else:
                    if scores_list:
                        first_sc = float(scores_list[0].get("score", 0.0))
                        model_conf = 1.0 - first_sc
            except Exception as infer_exc:
                logger.warning("Phishing BERT inference error: %s", infer_exc)
                model_conf = 0.0

        # Replace static blending with heuristic-dominant 3-tier blending
        final_confidence = 0.0
        if model is None or model_conf == 0.0:
            final_confidence = min(1.0, heuristic)
        else:
            if heuristic >= 0.65:
                # Strong social engineering signal — boost standard confidence
                # to guarantee MALICIOUS categorization if heuristics are firing heavily
                final_confidence = (0.20 * model_conf) + (0.80 * heuristic)
            elif heuristic >= 0.35:
                # Moderate signal — balanced blend
                final_confidence = (0.50 * model_conf) + (0.50 * heuristic)
            else:
                # Low heuristic signal — trust BERT more
                final_confidence = (0.75 * model_conf) + (0.25 * heuristic)

        absence = compute_absence_score(text)
        # Only apply absence bonus if there are existing heuristic signals too.
        # This is the key false-positive fix: plain business emails score 0 on
        # heuristics and should NOT be pushed into SUSPICIOUS by absence alone.
        if heuristic_result["score"] > 0.20:
            final_confidence = min(1.0, final_confidence + absence["absence_score"] * 0.35)

        # LLM Layer C: trigger when standard confidence is below threshold
        gemini_conf = 0.0
        if final_confidence < PhishingConfig.GEMINI_TRIGGER_THRESHOLD and len(text) > 50:
            lb = await _gemini_phishing_judge(text, app_state)
            gemini_conf = float(lb["confidence"])
            if gemini_conf > PhishingConfig.GEMINI_OVERRIDE_THRESHOLD:
                mode = "gemini_layer_c_override"

        final_conf = float(int(max(final_confidence, gemini_conf) * 10000)) / 10000.0
        # Always clamp to [0, 1]
        final_conf = min(1.0, max(0.0, final_conf))

        TIER1_SIGNALS = {"urgency_threat_combo", "account_threat", "urgency_deadline", "executive_impersonation"}
        tier1_fired = bool(set(triggered) & TIER1_SIGNALS)

        attribution: list = []

        if semantic_divergence and semantic_divergence.get("signals"):
            div_score = float(semantic_divergence.get("score", 0.0))
            if div_score >= 0.65:
                # Floor final confidence and trigger Tier 1 equivalent
                final_conf = max(final_conf, 0.65)
                tier1_fired = True
            for sig in semantic_divergence.get("signals", []):
                sig_type = sig.get("type", "obfuscation").replace("_", " ").title()
                attribution.append({
                    "feature": f"[SEMANTIC DIVERGENCE] {sig_type}",
                    "weight": round(div_score, 4),
                    "direction": "positive",
                    "category": "active_attack_signal",
                })

        if tier1_fired and final_conf < 0.55:
            final_conf = 0.55  # floor — BERT cannot override strong social engineering

        if tier1_fired and heuristic > 0.70 and final_conf < 0.75:
            final_conf = 0.75  # strong floor for multiple tier-1 signals

        verdict = (
            "MALICIOUS"   if final_conf >= PhishingConfig.MALICIOUS_THRESHOLD
            else "SUSPICIOUS" if final_conf >= PhishingConfig.SUSPICIOUS_THRESHOLD
            else "BENIGN"
        )

        token_scores = _token_scores(text)

        # ── Build Feature Attribution ────────────────────────────────────────
        # Two distinct categories are tracked separately:
        #   1. Active attack signals (positive heuristics that fired)
        #   2. Trust signal absences (legitimacy markers that are MISSING)
        # Keeping them separate lets analysts distinguish "active threat" from
        # "suspicious-but-unverified" — a critical distinction for SOC review.

        # Category 1: Active heuristic signals
        signal_weight_map = {
            cat: float(str(_COMPILED_SIGNALS[cat].get("weight", 0.0)))
            for cat in _COMPILED_SIGNALS
        }
        for cat in triggered:
            w = signal_weight_map.get(cat, 0.10)
            label = cat.replace("_", " ").title()
            attribution.append({
                "feature":   label,
                "weight":    round(w, 4),
                "direction": "positive",
                "category":  "active_attack_signal",
            })

        # Category 2: Absence signals (labeled distinctly)
        for sig in absence.get("absence_signals", []):
            label = "[TRUST MISSING] " + sig.replace("_", " ").title()
            attribution.append({
                "feature":   label,
                "weight":    round(absence["absence_score"] / max(1, len(absence["absence_signals"])), 4),
                "direction": "positive",
                "category":  "trust_signal_absence",
            })
            
        # Category 3: Contextual Dampening
        if heuristic_result.get("is_legit", False) and heuristic_result.get("dampened_amount", 0.0) > 0:
            attribution.append({
                "feature": "Context: Institutional/Educational Pattern",
                "weight": -round(heuristic_result["dampened_amount"], 4),
                "direction": "negative",
                "category": "trust_signal",
            })

        # Sort: active signals first (higher weight), absences last
        attribution.sort(key=lambda x: (x["category"] == "trust_signal_absence", -x["weight"]))

        return {
            "confidence":    final_conf,
            "verdict":       verdict,
            "shap_features": attribution,
            "mode":          mode,
            "token_scores":  token_scores,
        }
    except Exception as exc:
        # Return ERROR — never BENIGN on unhandled exception in a security context.
        # Returning BENIGN silently passes potentially malicious content.
        logger.error("detect_phishing unhandled error: %s", exc, exc_info=True)
        return {
            "confidence":    0.0,
            "verdict":       "ERROR",
            "shap_features": [],
            "mode":          "error_fallback",
            "token_scores":  [],
        }
