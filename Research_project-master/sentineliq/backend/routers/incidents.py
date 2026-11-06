import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException # type: ignore[import]
from db.database import get_incidents # type: ignore[import]

logger = logging.getLogger("sentineliq.incidents")
router = APIRouter()


@router.get("/incidents")
async def list_incidents(
    request: Request,
    limit: int = 20,
    threat_type: Optional[str] = None,
):
    """
    Return recent incidents from Firestore.
    If Firebase is offline, returns empty list (non-blocking).
    """
    try:
        limit = max(1, min(int(limit), 100))
        threat_filter = str(threat_type).strip() if threat_type else ""
        items = await get_incidents(limit=limit, threat_type=threat_filter)
        return {"incidents": items, "count": len(items)}
    except Exception as exc:
        logger.error("list_incidents failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not retrieve incidents.")
