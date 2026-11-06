import logging
import uuid
import asyncio
import datetime
from typing import Any, Dict, Optional
from firebase_admin import firestore  # type: ignore[import]

logger = logging.getLogger("sentineliq.firestore_writer")

async def write_incident(
    uid: Optional[str],
    engine_result: Dict[str, Any],
    threat_type: str,
    extension_version: str,
    source: str = "extension"
) -> None:
    """
    Write incident to Firestore under users/{uid}/incidents/{incident_id}.
    Called from analyze.py after scan completes.
    Only writes when source=='extension' and uid is present (A18).
    Never raises — all errors are logged as warnings.
    """
    # A18: Only write for extension-initiated scans with a verified uid
    if not uid or source != "extension":
        return

    try:
        db = firestore.client()

        # Use incident_id from engine if present (prevents duplicate writes on retry)
        incident_id = engine_result.get("incident_id")
        if not incident_id:
            incident_id = str(uuid.uuid4())

        # Map threat_type to human-readable label
        type_label = {
            "url":              "Malicious URL",
            "phishing":         "Phishing Attack",
            "prompt_injection": "Prompt Injection",
            "anomaly":          "Anomaly Detected",
            "email":            "Email Threat",
        }.get(threat_type, threat_type)

        verdict   = str(engine_result.get("verdict",   "BENIGN")).upper()
        risk_band = str(engine_result.get("risk_band", "")).upper()

        # Map verdict + risk_band to riskLevel
        if verdict == "MALICIOUS" or "CRITICAL" in risk_band:
            risk_level = "Critical"
        elif "HIGH" in risk_band:
            risk_level = "High"
        elif "MEDIUM" in risk_band or verdict == "SUSPICIOUS":
            risk_level = "Medium"
        else:
            risk_level = "Low"

        # Build incident document matching Section 4 schema exactly
        incident_doc: Dict[str, Any] = {
            "incident_id":        incident_id,
            "threat_type":        threat_type,
            "verdict":            verdict,
            "confidence":         float(engine_result.get("confidence",         0.0)),
            "risk_score":         int(engine_result.get("risk_score",           0)),
            "risk_band":          risk_band,
            "explanation":        str(engine_result.get("explanation",          "")),
            "action":             str(engine_result.get("action",               "")),
            "detection_mode":     str(engine_result.get("detection_mode",       "unknown")),
            "processing_time_ms": int(engine_result.get("processing_time_ms",   0)),
            "shap_features":      engine_result.get("shap_features",            []),
            # Frontend-normalised fields
            "type":               type_label,
            "riskLevel":          risk_level,
            "description":        str(engine_result.get("explanation",          "")),
            # Timestamps
            "timestamp":          engine_result.get(
                                      "timestamp",
                                      datetime.datetime.utcnow().isoformat() + "Z"
                                  ),
            # Provenance
            "source":             source,
            "browser":            "chrome",
            "extension_version":  extension_version,
        }

        incident_ref = (
            db.collection("users")
              .document(uid)
              .collection("incidents")
              .document(incident_id)
        )
        meta_ref = (
            db.collection("users")
              .document(uid)
              .collection("meta")
              .document("write_state")
        )

        # batch.commit() is synchronous — run in thread pool to avoid blocking event loop
        def _commit() -> None:
            batch = db.batch()
            batch.set(incident_ref, incident_doc)
            batch.set(
                meta_ref,
                {"last_write_timestamp": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            batch.commit()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _commit)

        logger.info("Wrote incident %s to Firestore for uid=%s…", incident_id, uid[:8])

    except Exception as exc:
        uid_safe = uid[:8] if uid else "none"
        logger.warning("Failed to write incident to Firestore for uid=%s…: %s", uid_safe, exc)

