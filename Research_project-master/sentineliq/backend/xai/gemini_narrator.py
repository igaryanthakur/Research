import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentineliq.narration")

# ── Quota / rate-limit cooldown tracker ───────────────────────────────────────
# When Gemini returns a 429 or quota-exhausted error we pause all Gemini calls
# for GEMINI_COOLDOWN_SECONDS so we stop hammering the API.
_gemini_quota_exceeded_until: float = 0.0   # epoch time
GEMINI_COOLDOWN_SECONDS: float = 300.0      # 5 minutes


def _is_quota_error(exc: Exception) -> bool:
    """Return True if the exception indicates a Gemini quota / rate-limit hit."""
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "quota", "rate limit", "resource_exhausted", "rateLimitExceeded".lower()))


def _mark_quota_exceeded() -> None:
    global _gemini_quota_exceeded_until
    _gemini_quota_exceeded_until = time.monotonic() + GEMINI_COOLDOWN_SECONDS
    logger.warning(
        "Gemini quota/rate-limit hit — entering offline-template mode for %.0f seconds.",
        GEMINI_COOLDOWN_SECONDS,
    )


def _gemini_in_cooldown() -> bool:
    return time.monotonic() < _gemini_quota_exceeded_until

# ── Three-tier templates for every threat × verdict combo ─────────────────────
TEMPLATES: Dict[str, Dict[str, Dict[str, str]]] = {
    "phishing": {
        "MALICIOUS": {
            "explanation": (
                "This message contains hallmark phishing indicators including credential-harvesting "
                "language and urgency cues designed to deceive the recipient. The behavioral "
                "patterns are consistent with a targeted spear-phishing campaign."
            ),
            "action": "Delete this message immediately and report it to your IT security team.",
        },
        "SUSPICIOUS": {
            "explanation": (
                "This message exhibits several characteristics associated with phishing attempts, "
                "though confidence is moderate. Review carefully before taking any action."
            ),
            "action": "Verify the sender through an independent channel before clicking any links.",
        },
        "BENIGN": {
            "explanation": "No significant phishing indicators were detected in this message.",
            "action": "No action required — this content appears safe.",
        },
    },
    "url": {
        "MALICIOUS": {
            "explanation": (
                "This URL exhibits multiple structural indicators of a malicious domain, including "
                "suspicious lexical patterns and deceptive redirects consistent with credential theft."
            ),
            "action": "Block this URL at the corporate firewall and report to the SOC.",
        },
        "SUSPICIOUS": {
            "explanation": (
                "This URL has some characteristics associated with potentially malicious sites. "
                "The domain structure or keywords warrant closer inspection."
            ),
            "action": "Do not visit this URL until it has been verified by your security team.",
        },
        "BENIGN": {
            "explanation": "This URL does not exhibit known malicious structural patterns.",
            "action": "No action required — this URL appears safe.",
        },
    },
    "prompt_injection": {
        "MALICIOUS": {
            "explanation": (
                "This input contains prompt injection patterns designed to override AI system "
                "instructions, hijack the model's role, or exfiltrate sensitive system context."
            ),
            "action": "Reject this input, reset the AI session context, and flag the user session.",
        },
        "SUSPICIOUS": {
            "explanation": (
                "This input shows weak signals of prompt injection intent. The phrasing "
                "partially resembles known override patterns but lacks definitive markers."
            ),
            "action": "Apply additional input validation and monitor this session.",
        },
        "BENIGN": {
            "explanation": "No prompt injection patterns detected in this input.",
            "action": "No action required — this input appears safe.",
        },
    },
    "anomaly": {
        "MALICIOUS": {
            "explanation": (
                "This session exhibits behavioral anomalies that deviate significantly from the "
                "established baseline, including unusual access patterns and privilege signals."
            ),
            "action": "Force multi-factor authentication and lock the account pending investigation.",
        },
        "SUSPICIOUS": {
            "explanation": (
                "This session shows moderate deviations from normal behavior. "
                "Some access parameters fall outside the expected range."
            ),
            "action": "Flag this session for manual review and apply step-up authentication.",
        },
        "BENIGN": {
            "explanation": "This session's behavioral profile is within normal parameters.",
            "action": "No action required — this session appears normal.",
        },
    },
}


def _get_template(threat_type: str, verdict: str) -> Dict[str, str]:
    """Return explanation+action template for given threat × verdict."""
    type_templates = TEMPLATES.get(threat_type, TEMPLATES["phishing"])
    # Normalise verdict — treat anything not in template as BENIGN
    verd_key = verdict if verdict in type_templates else "BENIGN"
    return type_templates[verd_key]


async def get_narration(
    threat_type: str,
    verdict: str,
    shap_features: List[Dict[str, Any]],
    snippet: str,
    app_state: Any,
) -> Dict[str, str]:
    """
    Three-tier narration:
      Tier 1 — Gemini 2.0 Flash, 4s timeout
      Tier 2 — Gemini shorter fallback prompt, 3s timeout
      Tier 3 — Offline template (always non-empty)

    Returns: { explanation, action, narration_mode }
    """
    template = _get_template(threat_type, verdict)

    client: Optional[Any] = getattr(app_state, "gemini_client", None)
    gemini_available: bool = bool(getattr(app_state, "gemini_available", False))

    if not gemini_available or client is None:
        return {
            "explanation": template["explanation"],
            "action": template["action"],
            "narration_mode": "offline_template",
        }

    from typing import cast
    # Build top features string
    top_features = ", ".join(
        str(cast(dict, f).get("feature", "")) for f in shap_features[:3] if isinstance(f, dict) and cast(dict, f).get("feature")
    )
    safe_snippet = str(snippet)[:200]  # type: ignore[index]

    # ── Tier 1 prompt ──────────────────────────────────────────────────────────
    prompt_t1 = (
        f"You are SentinelIQ, an enterprise cybersecurity AI analyst.\n"
        f"A {threat_type} scan produced verdict: {verdict}.\n"
        f"Top risk factors: {top_features or 'N/A'}.\n"
        f'Analysed snippet: """{safe_snippet}"""\n\n'
        f"Respond in EXACTLY this format — no markdown, no extra text:\n"
        f"Explanation: [Two clear professional sentences explaining why this was flagged.]\n"
        f"Action: [One clear sentence recommending what a security analyst should do.]\n"
    )

    # ── Tier 2 shorter prompt ──────────────────────────────────────────────────
    prompt_t2 = (
        f"Cybersecurity verdict: {threat_type} → {verdict}.\n"
        f"Explain in 2 sentences and give 1 action sentence.\n"
        f"Format: Explanation: ... Action: ...\n"
    )

    # Skip Gemini entirely if we are in cooldown after a quota error
    if _gemini_in_cooldown():
        return {
            "explanation": template["explanation"],
            "action": template["action"],
            "narration_mode": "offline_template_quota_cooldown",
        }

    for tier, prompt, timeout in [
        ("gemini_tier1", prompt_t1, 15.0),
        ("gemini_tier2", prompt_t2, 8.0),
    ]:
        try:
            _client = client
            _prompt = prompt

            async def _call() -> Any:
                response = await _client.chat.completions.create(
                    model="mistralai/Mistral-7B-Instruct-v0.2",
                    messages=[{"role": "user", "content": _prompt}],
                )
                return response

            response: Any = await asyncio.wait_for(
                _call(),
                timeout=timeout,
            )

            raw = str(response.choices[0].message.content).strip()

            # Parse by splitting on "Action:"
            if "Action:" in raw:
                parts = raw.split("Action:", 1)
                explanation_raw = parts[0].replace("Explanation:", "").strip()
                action_raw = parts[1].strip()

                explanation = " ".join(explanation_raw.splitlines()).strip()
                action = " ".join(action_raw.splitlines()).strip()

                if explanation and action:
                    return {
                        "explanation": explanation,
                        "action": action,
                        "narration_mode": tier,
                    }
        except asyncio.TimeoutError:
            logger.warning("Gemini narration %s timed out.", tier)
        except Exception as exc:
            if _is_quota_error(exc):
                _mark_quota_exceeded()
                break  # skip tier 2 — quota is exhausted
            logger.warning("Gemini narration %s failed: %s", tier, exc)

    # Tier 3 — offline template always succeeds
    return {
        "explanation": template["explanation"],
        "action": template["action"],
        "narration_mode": "offline_template",
    }
