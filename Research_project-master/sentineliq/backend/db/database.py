import os
import json
import logging
from typing import List

import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import credentials, firestore  # type: ignore[import-untyped]
from fastapi import FastAPI  # type: ignore[import-untyped]

logger = logging.getLogger("sentineliq.db")

_db = None  # Global Firestore client — None when offline


async def init_firebase(app: FastAPI) -> None:  # type: ignore[misc]
    """Initialize Firebase Admin SDK. Stores mode in app.state.firebase_mode."""
    global _db
    sa_path = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT", "./firebase-service-account.json"
    )

    # ── Pre-flight checks ────────────────────────────────────────────────────
    if not os.path.exists(sa_path):
        app.state.firebase_mode = "offline_no_service_account"
        logger.warning(
            "❌ firebase-service-account.json not found at '%s' — running offline.\n"
            "   Fix: Place a valid service-account JSON file at that path.",
            sa_path,
        )
        return

    # Read project_id for diagnostic logging
    try:
        with open(sa_path, "r", encoding="utf-8") as fh:
            sa_data = json.load(fh)
        project_id: str = sa_data.get("project_id", "unknown")
        logger.info("🔑 Firebase service account loaded — project: %s", project_id)
    except Exception as read_exc:
        logger.warning("Could not read service-account JSON for diagnostics: %s", read_exc)
        project_id = "unknown"

    try:
        cred = credentials.Certificate(sa_path)
        firebase_admin.initialize_app(cred)
        _db = firestore.client()
        app.state.firebase_mode = f"firestore_connected:{project_id}"
        logger.info("✅ Firebase Firestore connected (project: %s).", project_id)

    except firebase_admin.exceptions.AlreadyExistsError:
        # App already initialised — re-use existing client (happens on hot-reload)
        _db = firestore.client()
        app.state.firebase_mode = f"firestore_connected:{project_id}"
        logger.info("✅ Firebase app already initialised — re-using client.")

    except Exception as exc:
        err_str = str(exc)
        app.state.firebase_mode = ("error:" + err_str)[:64]  # type: ignore[assignment]

        if "NOT_FOUND" in err_str or "not found" in err_str.lower():
            logger.error(
                "❌ Firebase Firestore database NOT provisioned for project '%s'.\n"
                "   Fix: Go to https://console.firebase.google.com/project/%s/firestore\n"
                "        → Click 'Create database' → choose a region → Start in test mode.",
                project_id, project_id,
            )
        else:
            logger.error("❌ Firebase init failed: %s", exc)


async def save_incident(data: dict) -> bool:
    """Fire-and-forget Firestore write. Returns False silently if offline."""
    if _db is None:
        return False
    try:
        _db.collection("incidents").document(data["incident_id"]).set(data)
        return True
    except Exception as exc:
        logger.warning("save_incident failed (non-fatal): %s", exc)
        return False


async def get_incidents(limit: int = 20, threat_type: str = "") -> List[dict]:
    """Fetch recent incidents from Firestore. Returns [] if offline."""
    if _db is None:
        return []
    try:
        q = _db.collection("incidents").order_by(
            "timestamp", direction=firestore.Query.DESCENDING # type: ignore
        )
        if threat_type:
            q = q.where("threat_type", "==", threat_type)
        q = q.limit(limit)
        results = [doc.to_dict() for doc in q.stream()]
        return [r for r in results if r is not None] # type: ignore
    except Exception as exc:
        logger.warning("get_incidents failed (non-fatal): %s", exc)
        return []


async def get_historical_rate(threat_type: str) -> float:
    """Returns fraction of recent incidents that were MALICIOUS for given type."""
    if _db is None:
        return 0.0
    try:
        docs = (
            _db.collection("incidents")
            .where("threat_type", "==", threat_type)
            .order_by("timestamp", direction=firestore.Query.DESCENDING) # type: ignore
            .limit(50)
            .stream()
        )
        records = [doc.to_dict() for doc in docs]
        valid_records = [r for r in records if r is not None]
        if not valid_records:
            return 0.0
        malicious: int = sum(1 for r in valid_records if r.get("verdict") == "MALICIOUS")
        ratio: float = malicious / len(valid_records)
        return round(ratio, 4)  # type: ignore[return-value]
    except Exception:
        return 0.0
