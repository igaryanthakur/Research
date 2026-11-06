import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("sentineliq.scoring")

# Severity of each threat class
SEVERITY_WEIGHTS: Dict[str, float] = {
    "prompt_injection": 1.00,
    "phishing":         0.90,
    "url":              0.80,
    "anomaly":          0.70,
}

# Verdict multiplier — BENIGN findings should score near-zero
_VERDICT_MULTIPLIERS: Dict[str, float] = {
    "MALICIOUS":  1.00,
    "SUSPICIOUS": 0.55,
    "BENIGN":     0.04,
}

# Calibrated per-engine confidence thresholds (lower = catch more)
OPTIMAL_THRESHOLDS: Dict[str, float] = {
    "phishing":         0.55,
    "url":              0.60,   # Aligned with url_detector._THRESHOLD_MALICIOUS
    "prompt_injection": 0.38,
    "anomaly":          0.48,
}


def get_verdict_for_engine(engine: str, confidence: float) -> str:
    """
    Apply engine-specific threshold to produce verdict.
    Centralised so engines and this module stay in sync.
    """
    threshold = OPTIMAL_THRESHOLDS.get(engine, 0.50)
    if confidence >= threshold + 0.20:
        return "MALICIOUS"
    elif confidence >= threshold:
        return "SUSPICIOUS"
    return "BENIGN"


def compute_risk(
    confidence: Any,
    threat_type: str,
    shap_features: List[Any],
    historical_rate: float = 0.0,
    verdict: str = "BENIGN",
    escalation_bonus: int = 0,
) -> Tuple[int, str]:
    """
    Composite risk score (0–100) and risk band.

    Formula:
      50% — model confidence          (primary signal)
      30% — severity × verdict_mult   (threat class × verdict gating)
      15% — historical malicious rate
       5% — SHAP richness (capped at 3 features)

    Plus escalation_bonus from ensemble voter (0, 8, 15, or 30 points).

    Returns: (score: int 0–100, band: CRITICAL|HIGH|MEDIUM|LOW)
    """
    conf = min(1.0, max(0.0, float(confidence)))
    severity = float(SEVERITY_WEIGHTS.get(str(threat_type), 0.50))
    v_mult = float(_VERDICT_MULTIPLIERS.get(str(verdict).upper(), 0.04))
    hist = min(1.0, max(0.0, float(historical_rate)))
    shap_richness = min(1.0, float(len(shap_features)) / 3.0)

    raw = (
        0.50 * conf
        + 0.30 * (severity * v_mult)
        + 0.15 * hist
        + 0.05 * shap_richness
    )

    base_score = int(round(raw * 100))
    score = int(max(0, min(100, base_score + int(escalation_bonus))))

    band = (
        "CRITICAL" if score >= 80
        else "HIGH"   if score >= 60
        else "MEDIUM" if score >= 35
        else "LOW"
    )

    return score, band
