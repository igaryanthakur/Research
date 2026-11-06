"""
scoring/ensemble.py — Cross-engine ensemble voter.

When multiple engines flag the same input, their agreement is a far
stronger signal than any single-engine score.  This module sits on top
of all 4 engines and provides a composite verdict + escalation bonus.
"""

from typing import Any, Dict, List

# ── Engine weights (must sum to 1.0) ───────────────────────────────────────
ENGINE_WEIGHTS: Dict[str, float] = {
    "phishing":        0.30,
    "url":             0.25,
    "prompt_injection":0.28,
    "anomaly":         0.17,
}

# Confidence threshold for a vote to count as "MALICIOUS"
_VOTE_THRESHOLD = 0.45


def ensemble_vote(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate results from multiple engines into a composite verdict.

    Each result dict must have:
        engine      : str   — one of ENGINE_WEIGHTS keys
        verdict     : str   — MALICIOUS | SUSPICIOUS | BENIGN
        confidence  : float — 0.0 – 1.0

    Returns:
        malicious_votes      : int   — engines that flagged MALICIOUS
        suspicious_votes     : int   — engines that flagged SUSPICIOUS
        weighted_confidence  : float — weight-normalised composite confidence
        escalation_bonus     : int   — points to add to risk score (0, 15, or 30)
        cross_engine_verdict : str   — MALICIOUS | SUSPICIOUS | CLEAN
        engines_fired        : list  — names of engines that voted MALICIOUS
    """
    malicious_votes = 0
    suspicious_votes = 0
    total_weight = 0.0
    weighted_conf = 0.0
    engines_fired: List[str] = []

    for r in results:
        engine = str(r.get("engine", ""))
        verdict = str(r.get("verdict", "BENIGN")).upper()
        conf = float(r.get("confidence", 0.0))
        weight = float(ENGINE_WEIGHTS.get(engine, 0.25))

        # Weighted Confidence Doesn't Respect Verdict fix:
        # A 0.95 BENIGN shouldn't contribute strongly to a MALICIOUS ensemble score.
        if verdict == "BENIGN":
            conf *= 0.25

        weighted_conf += conf * weight
        total_weight += weight

        if verdict == "MALICIOUS" and conf >= _VOTE_THRESHOLD:
            malicious_votes += 1 # type: ignore[operator]
            engines_fired.append(engine)
        elif verdict in ("SUSPICIOUS", "MALICIOUS") and conf >= 0.25:
            suspicious_votes += 1 # type: ignore[operator]
            if verdict == "MALICIOUS":
                engines_fired.append(engine)

    # Normalise weighted confidence
    normalised_conf = float(round(weighted_conf / total_weight, 4)) if total_weight > 0 else 0.0 # type: ignore[call-overload]

    # Escalation bonus added to final risk_score
    if malicious_votes >= 3:
        escalation_bonus = 30   # 3+ engines agree — near-certain threat
        cross_verdict = "MALICIOUS"
    elif malicious_votes >= 2:
        escalation_bonus = 15   # 2 engines agree — strong signal
        cross_verdict = "MALICIOUS"
        # Narrow cross-engine escalation fix: URL + Phishing is critical
        if "url" in engines_fired and "phishing" in engines_fired:
            escalation_bonus += 10 # Extra penalty for credential harvest
    elif malicious_votes == 1 and suspicious_votes >= 1:
        escalation_bonus = 8    # one MALICIOUS + one SUSPICIOUS = elevate
        cross_verdict = "SUSPICIOUS"
    elif suspicious_votes >= 2:
        escalation_bonus = 5
        cross_verdict = "SUSPICIOUS"
    else:
        escalation_bonus = 0
        cross_verdict = "CLEAN"

    return {
        "malicious_votes":     malicious_votes,
        "suspicious_votes":    suspicious_votes,
        "weighted_confidence": normalised_conf,
        "escalation_bonus":    escalation_bonus,
        "cross_engine_verdict":cross_verdict,
        "engines_fired":       engines_fired,
    }

def cross_engine_escalate(results: List[Dict[str, Any]]) -> float:
    """
    Generalised cross-engine escalation.
    If multiple engines (e.g. url + phishing) both flag the input,
    escalate the confidence.
    """
    highest_conf = 0.0
    malicious_count = 0
    suspicious_count = 0

    for r in results:
        conf = float(r.get("confidence", 0))
        verdict = str(r.get("verdict", "BENIGN")).upper()
        
        highest_conf = max(highest_conf, conf)
        if verdict == "MALICIOUS":
            malicious_count += 1
        elif verdict == "SUSPICIOUS":
            suspicious_count += 1

    if malicious_count >= 2:
        # Multiple engines agree — very high confidence
        combined = highest_conf + 0.15
        return min(1.0, combined)

    if malicious_count == 1 and suspicious_count >= 1:
        # One malicious, one suspicious
        return min(1.0, highest_conf + 0.08)

    return highest_conf  # no escalation
