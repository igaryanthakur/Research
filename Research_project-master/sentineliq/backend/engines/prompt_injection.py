"""
Prompt Injection Detection Engine
==================================
Layer A : Regex (all patterns from config.py) + homoglyph normalization
Layer B : LLM AI cross-check

All patterns, thresholds, and constants come from config.py.
Patterns are compiled once at module startup, never inside detect functions.
"""

import re
import json
import asyncio
import logging
import time
import unicodedata
import cachetools  # type: ignore[import]
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI  # type: ignore[import-untyped]

logger = logging.getLogger("sentineliq.injection")

from config import InjectionConfig, HOMOGLYPH_MAP  # type: ignore[import]

# ─── Homoglyph normalization ──────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """NFKD decomposition + homoglyph substitution for evasion resistance."""
    text = unicodedata.normalize("NFKD", str(text))
    for fake, real in HOMOGLYPH_MAP.items():
        text = text.replace(fake, real)
    return text


# ─── Pattern compilation (at module load, never in detect functions) ──────────
# Patterns come entirely from InjectionConfig.PATTERNS — no inline strings here.

_COMPILED: Dict[str, List[re.Pattern]] = {}

def _compile_all() -> None:
    global _COMPILED
    seen: set = set()
    _COMPILED = {}
    for category, raw_list in InjectionConfig.PATTERNS.items():
        compiled: List[re.Pattern] = []
        for p in raw_list:
            if p in seen:
                continue  # deduplicate
            seen.add(p)
            try:
                compiled.append(re.compile(p, re.IGNORECASE | re.UNICODE | re.DOTALL))
            except re.error as exc:
                logger.warning("Injection regex compile error in %s: %s", category, exc)
        _COMPILED[category] = compiled

_compile_all()


# ─── Startup ──────────────────────────────────────────────────────────────────

async def compile_patterns(app: "FastAPI") -> None:  # type: ignore[misc]
    """Attach compiled patterns and session cache to app.state at startup."""
    app.state.pi_patterns = _COMPILED
    app.state.injection_mode = "regex_plus_gemini"
    total = sum(len(v) for v in _COMPILED.values())
    app.state.pi_session_cache = cachetools.TTLCache(
        maxsize=InjectionConfig.SESSION_CACHE_SIZE,
        ttl=InjectionConfig.SESSION_CACHE_TTL,
    )
    logger.info(
        "Prompt injection: %d patterns across %d categories. Session cache initialized.",
        total, len(_COMPILED),
    )


# ─── Layer A: Regex scan ──────────────────────────────────────────────────────

def _layer_a(text: str) -> Dict[str, Any]:
    """
    Runs all patterns against both original and homoglyph-normalised text.
    Returns: score, matched_categories, matched_snippets.
    """
    text_norm = _normalize(text)
    matched_categories: List[str] = []
    matched_snippets: List[str] = []

    for category, patterns in _COMPILED.items():
        for p in patterns:
            m = p.search(text) or p.search(text_norm)
            if m:
                matched_categories.append(category)
                matched_snippets.append(m.group(0)[:200])  # cap snippet length
                break

    score: float = 0.0
    if matched_categories:
        score = max(InjectionConfig.SEVERITY.get(cat, 0.5) for cat in matched_categories)

    return {
        "score":               score,
        "matched_categories":  matched_categories,
        "matched_snippets":    matched_snippets,
    }


# ─── Layer B: LLM judge ────────────────────────────────────────────────────

async def _layer_b_gemini(text: str, app_state: Any) -> Dict[str, Any]:
    """Calls LLM with structured prompt from config. Returns 0.0 on any failure."""
    if not getattr(app_state, "gemini_available", False):
        return {"confidence": 0.0, "reason": "Gemini unavailable"}

    client: Optional[Any] = getattr(app_state, "gemini_client", None)
    if client is None:
        return {"confidence": 0.0, "reason": "No Gemini client"}

    snippet = str(text)[:500]
    prompt = InjectionConfig.GEMINI_JUDGE_PROMPT.format(user_input=snippet)

    _fallback = {"confidence": 0.0, "reason": "Gemini offline fallback"}

    for attempt in range(2):
        try:
            _c, _p = client, prompt

            async def _call() -> Any:
                response = await _c.chat.completions.create(
                    model="mistralai/Mistral-7B-Instruct-v0.2",
                    messages=[{"role": "user", "content": _p}],
                )
                return response

            timeout = (
                15.0
                if attempt == 0
                else 8.0
            )
            response: Any = await asyncio.wait_for(
                _call(),
                timeout=timeout,
            )
            raw: str = str(response.choices[0].message.content).strip()

            # Strip markdown fences
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return _fallback

            is_injection = bool(parsed.get("is_injection", False))
            conf = float(parsed.get("confidence", 0.5))
            conf = min(1.0, max(0.0, conf))

            # Normalize: if not injection, flip confidence
            if not is_injection:
                conf = 1.0 - conf

            return {
                "confidence": round(conf, 4),
                "reason":     str(parsed.get("reasoning", parsed.get("reason", ""))),
            }

        except asyncio.TimeoutError:
            if attempt == 0:
                await asyncio.sleep(InjectionConfig.GEMINI_RETRY_DELAY)
                continue
            return _fallback
        except Exception as exc:
            logger.warning("Gemini Layer B injection failed (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                await asyncio.sleep(InjectionConfig.GEMINI_RETRY_DELAY)
                continue
            return _fallback

    return _fallback


# ─── Public entry point ───────────────────────────────────────────────────────

async def detect_injection(
    text: str,
    app_state: Any,
    session_id: Optional[str] = None,
    escalation_mode: bool = False,
) -> Dict[str, Any]:
    """
    Two-layer prompt injection detector with stateful session memory.
    Never raises.
    """
    try:
        mode: str = getattr(app_state, "injection_mode", "regex_only")

        # Session memory context (multi-turn drip detection)
        session_cache = getattr(app_state, "pi_session_cache", None)
        context_text = str(text)

        if session_id and session_cache is not None:
            history: List[str] = session_cache.get(session_id, [])
            history.append(context_text)
            history = history[-InjectionConfig.SESSION_HISTORY_DEPTH:]
            session_cache[session_id] = history
            if len(history) > 1:
                context_text = "\n---\n".join(history)
                mode = "stateful_regex_plus_gemini"

        # Layer A
        la = _layer_a(context_text)
        layer_a_score: float = float(la["score"])

        # Layer B: LLM validation. Use regex only for candidate generation.
        # Let LLM validation decide final verdict to prevent false positives on benign AI prompts.
        run_b = layer_a_score > 0.0 and getattr(app_state, "gemini_available", False)
        if run_b:
            lb = await _layer_b_gemini(context_text, app_state)
            layer_b_score  = float(lb["confidence"])
            layer_b_reason = str(lb.get("reason", ""))
            
            # LLM decides final verdict
            combined = layer_b_score
        else:
            combined = layer_a_score

        # Platt calibration
        try:
            from xai.calibrator import calibrate_confidence  # type: ignore[import]
            combined = calibrate_confidence("prompt_injection", combined)
        except Exception:
            pass

        combined = min(1.0, max(0.0, combined))

        effective_malicious = (
            InjectionConfig.MALICIOUS_THRESHOLD - 0.08
            if escalation_mode else
            InjectionConfig.MALICIOUS_THRESHOLD
        )
        effective_suspicious = (
            InjectionConfig.SUSPICIOUS_THRESHOLD - 0.05
            if escalation_mode else
            InjectionConfig.SUSPICIOUS_THRESHOLD
        )

        verdict: str = (
            "MALICIOUS" if combined >= effective_malicious
            else "SUSPICIOUS" if combined >= effective_suspicious
            else "BENIGN"
        )

        shap_features = [
            {
                "feature":   cat.replace("_", " "),
                "weight":    round(InjectionConfig.SEVERITY.get(cat, 0.5), 4),
                "direction": "positive",
            }
            for cat in la["matched_categories"]
        ]

        return {
            "confidence":       round(combined, 4),
            "verdict":          verdict,
            "shap_features":    shap_features,
            "layer_a_score":    layer_a_score,
            "layer_b_score":    layer_b_score,
            "matched_patterns": la["matched_snippets"],
            "reason":           layer_b_reason,
            "mode":             mode,
        }
    except Exception as exc:
        logger.error("detect_injection unhandled error: %s", exc, exc_info=True)
        # SECURITY: return ERROR, not BENIGN. A silent pass-through on unhandled
        # exceptions is a security bug — it allows injections to be missed when
        # the engine faults. Upstream pipeline must handle ERROR explicitly.
        return {
            "confidence":       0.0,
            "verdict":          "ERROR",
            "shap_features":    [],
            "layer_a_score":    0.0,
            "layer_b_score":    0.0,
            "matched_patterns": [],
            "reason":           f"Engine error: {exc}",
            "mode":             "error_fallback",
        }
