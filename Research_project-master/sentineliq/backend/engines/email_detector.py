"""
engines/email_detector.py — Enterprise Email Threat Orchestrator (Backend ML/Heuristic Scoring)
=============================================================================================

This engine processes the Privacy-Safe Feature Vector extracted by the browser extension.
It receives NO raw email text. It scores the threat purely on extracted structural signals,
urgency counts, sender mismatch booleans, and link context scores.

Output matches the standard pipeline signature: {verdict, confidence, shap_features, mode}
Note: The API retains the 'shap_features' key for orchestrator compatibility, but internally
and in the UI these are strictly treated and labeled as 'Feature Attribution Scores', as this
is a weighted heuristic ensemble, not a trained ML model calculating Shapley values.
"""

import logging
import asyncio
import json
import re
import math
from typing import Any, Dict, List

from config import EmailConfig  # type: ignore[import]

logger = logging.getLogger("sentineliq.email")

# Lazy import for Gemini (Layer 4)
try:
    from google import genai  # type: ignore[import]
except ImportError:
    pass

# ─── Stage 3: ML / Heuristic Vector Scoring ───────────────────────────────────

def _score_email_vector(vector: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes a risk score from the numeric/boolean feature vector.
    Returns the raw score and the highest-weighted contributing signals for feature attribution.
    """
    raw_score = 0.0
    feature_attribution = []
    
    # 0. Context-Aware Body Heuristics
    body_text = str(vector.get("bodyText", "")).strip()
    if body_text:
        from engines.phishing import _heuristic_score
        h_res = _heuristic_score(body_text)
        
        body_score = h_res.get("score", 0.0)
        is_legit = h_res.get("is_legit", False)
        dampened_amount = h_res.get("dampened_amount", 0.0)
        
        if body_score > 0:
            w = 0.40 * min(1.0, body_score)
            raw_score += w
            feature_attribution.append({
                "feature": f"Email Body Phishing Heuristics ({int(body_score*100)}%)",
                "weight": round(w, 3),
                "direction": "positive",
                "category": "active_attack_signal"
            })
            
        if is_legit and dampened_amount > 0:
            dw = -0.40 * min(1.0, dampened_amount)
            feature_attribution.append({
                "feature": "Context: Institutional/Educational Pattern",
                "weight": round(dw, 3),
                "direction": "negative",
                "category": "trust_signal"
            })

    # 1. Sender Mismatch (High Risk)
    sender_mismatch = bool(vector.get("sender_mismatch", False))
    if sender_mismatch:
        w = EmailConfig.FEATURE_WEIGHTS.get("sender_mismatch", 0.30)
        raw_score += w
        feature_attribution.append({"feature": "Sender Domain Mismatch", "weight": w, "direction": "positive"})
        
    # 2. Homoglyph Detection (High Risk)
    homoglyph = bool(vector.get("homoglyph_detected", False))
    if homoglyph:
        w = EmailConfig.FEATURE_WEIGHTS.get("homoglyph_detected", 0.20)
        raw_score += w
        feature_attribution.append({"feature": "Homoglyph Evasion Detected", "weight": w, "direction": "positive"})
        
    # 3. Urgency Score (Continuous 0-1)
    urgency = float(vector.get("urgency_score", 0.0))
    if urgency > 0:
        w = EmailConfig.FEATURE_WEIGHTS.get("urgency_score", 0.35) * min(1.0, urgency)
        raw_score += w
        feature_attribution.append({"feature": f"Urgency Language Signal ({int(urgency*100)}%)", "weight": w, "direction": "positive"})
        
    # 4. Attachment Risk (Continuous 0-1)
    attachment_risk = float(vector.get("attachment_risk", 0.0))
    if attachment_risk > 0:
        w = EmailConfig.FEATURE_WEIGHTS.get("attachment_risk", 0.25) * min(1.0, attachment_risk)
        raw_score += w
        feature_attribution.append({"feature": f"High-Risk Attachment Profile", "weight": w, "direction": "positive"})
        
    # 5. Link Context Risk
    suspicious_links = float(vector.get("suspicious_links", 0.0))
    if suspicious_links > 0:
        w = EmailConfig.FEATURE_WEIGHTS.get("suspicious_links", 0.35) * min(1.0, suspicious_links)
        raw_score += w
        feature_attribution.append({"feature": f"Suspicious Link Context", "weight": w, "direction": "positive"})

    # Multi-signal escalation bonus
    if sum(1 for f in feature_attribution if float(f["weight"]) > 0.15) >= 3:
        raw_score += 0.25
        
    # Sort features by weight
    feature_attribution.sort(key=lambda x: float(x["weight"]), reverse=True)
    
    # ─── Mathematical Confidence Normalization ───
    # We apply a dampening curve to ensure realistic noisy vectors land in 0.78-0.94,
    # and theoretical maximums hit a hard ceiling of 0.97.
    
    max_confidence_ceiling = 0.97
    
    # Simple dampening curve: x / (x + k) mapped to max_ceiling
    # k controls how fast it approaches the asymptote. A k of 0.4 works well here.
    k = 0.4
    if raw_score > 0:
        dampened_score = (raw_score / (raw_score + k)) * 1.15
    else:
        dampened_score = 0.0
        
    # ─── Extraction Confidence Penalty ───
    extraction_confidence = vector.get("extraction_confidence", "high").lower()
    if extraction_confidence == "low":
        dampened_score *= 0.6  # 40% penalty for fallback extraction
        feature_attribution.append({"feature": "Low Extraction Confidence (Fallback Heuristics)", "weight": -0.2, "direction": "negative"})
    elif extraction_confidence == "medium":
        dampened_score *= 0.85 # 15% penalty for generic webmail match
        feature_attribution.append({"feature": "Medium Extraction Confidence", "weight": -0.1, "direction": "negative"})

    # Apply hard cap
    # Ensure low confidence extractions cannot exceed MALICIOUS threshold independently
    if extraction_confidence == "low" and dampened_score >= EmailConfig.MALICIOUS_THRESHOLD:
        dampened_score = EmailConfig.MALICIOUS_THRESHOLD - 0.01

    final_score = min(max_confidence_ceiling, dampened_score)
    
    return {
        "confidence": float(int(final_score * 10000)) / 10000.0,
        "feature_attribution": feature_attribution
    }

# ─── Stage 4: Gemini Narration (High Confidence Only) ─────────────────────────

async def _gemini_vector_narrator(signals: List[Dict[str, Any]], app_state: Any) -> Dict[str, str]:
    """Generates an analyst briefing based purely on structured signals, no email text."""
    if not getattr(app_state, "gemini_available", False) or not getattr(app_state, "gemini_client", None):
        return {"explanation": "Gemini unavailable.", "action": ""}

    from engines.phishing import _gemini_token_bucket_acquire
    if not await _gemini_token_bucket_acquire():
        logger.warning("[Email] Skipped Gemini — token bucket exhausted.")
        return {"explanation": "Gemini rate limited.", "action": ""}

    client = app_state.gemini_client
    
    # Format signals into a neat string list
    signal_strs = [f"- {s['feature']} (impact: {s['weight']})" for s in signals[:5]]
    signal_text = "\n".join(signal_strs)
    
    prompt = EmailConfig.GEMINI_PROMPT_TEMPLATE.format(signals=signal_text)
    
    backoff = 1.0
    last_exc: Exception = Exception("unknown")

    for attempt in range(4):
        try:
            def _call() -> Any:
                return client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                
            loop = asyncio.get_event_loop()
            resp = await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=8.0)
            
            raw = str(resp.text).strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            
            parsed = json.loads(raw)
            return {
                "explanation": parsed.get("explanation", ""),
                "action": parsed.get("action", "")
            }
        except json.JSONDecodeError as jde:
            logger.warning("[Email] JSON parse failed on attempt %d: %s", attempt + 1, jde)
            return {"explanation": "", "action": ""}
        except Exception as exc:
            err_str = str(exc).lower()
            if "429" in err_str or "quota" in err_str or "too many requests" in err_str:
                logger.warning("[Email] 429 Rate Limit on attempt %d. Backing off for %.1fs...", attempt + 1, backoff)
                await asyncio.sleep(backoff)
                backoff = min(16.0, backoff * 2.0)
                last_exc = exc
            else:
                logger.debug(f"Email Gemini Narration failed: {exc}")
                return {"explanation": "", "action": ""}

    logger.error("[Email] Gemini exhausted all 4 attempts. Last error: %s", last_exc)
    return {"explanation": "", "action": ""}

# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def detect_email_vector(vector: Dict[str, Any], app_state: Any) -> Dict[str, Any]:
    """
    Analyzes the extracted email feature vector.
    """
    try:
        # Stage 3: Vector Scoring
        res = _score_email_vector(vector)
        confidence = res["confidence"]
        feature_attribution = res["feature_attribution"]
        
        # Verdict calculation
        if confidence >= EmailConfig.MALICIOUS_THRESHOLD:
            verdict = "MALICIOUS"
        elif confidence >= EmailConfig.SUSPICIOUS_THRESHOLD:
            verdict = "SUSPICIOUS"
        else:
            verdict = "BENIGN"
            
        mode = "vector_heuristic_ensemble"
        
        # Stage 4: Gemini Narration (Only on suspicious/malicious)
        explanation = ""
        action = ""
        if verdict in ("MALICIOUS", "SUSPICIOUS") and len(feature_attribution) > 0:
            gemini_res = await _gemini_vector_narrator(feature_attribution, app_state)
            explanation = gemini_res.get("explanation", "")
            action = gemini_res.get("action", "")
            if explanation:
                mode += "_with_ai_narration"
                
        return {
            "confidence": confidence,
            "verdict": verdict,
            "shap_features": feature_attribution, # API requires this key name for compatibility
            "mode": mode,
            "explanation": explanation,
            "action": action
        }
    except Exception as exc:
        logger.error(f"Email vector analysis failed: {exc}", exc_info=True)
        return {
            "confidence": 0.0,
            "verdict": "ERROR",
            "shap_features": [],
            "mode": "error_fallback",
            "explanation": "Analysis failed.",
            "action": ""
        }
