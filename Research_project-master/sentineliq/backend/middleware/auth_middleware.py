import logging
from typing import Callable, Any
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from firebase_admin import auth as firebase_auth  # type: ignore[import]

logger = logging.getLogger("sentineliq.auth_middleware")

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        # Only apply to /api/v1/analyze
        if not request.url.path.startswith("/api/v1/analyze"):
            return await call_next(request)

        # 1. Parse Version and Escalation Headers
        version = request.headers.get("X-Extension-Version", "")
        request.state.extension_version = version

        escalation_str = request.headers.get("X-Escalation-Mode", "false").lower()
        request.state.escalation_mode = escalation_str == "true"

        # 2. Check Authorization Header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # Anonymous scan
            request.state.uid = None
            request.state.email = ""
            request.state.source = "anonymous"
            return await call_next(request)

        token = auth_header.split(" ")[1]

        # 3. Verify Token
        try:
            # check_revoked=True is mandatory for security
            decoded = firebase_auth.verify_id_token(token, check_revoked=True)
            uid = decoded.get("uid")
            
            if not uid:
                raise ValueError("Token missing uid")

            request.state.uid = uid
            request.state.email = decoded.get("email", "")
            request.state.source = "extension"

            # Log only truncated uid
            logger.debug(f"Auth successful for uid={uid[:8]}...")
            
            return await call_next(request)

        except firebase_auth.ExpiredIdTokenError:
            logger.warning("Firebase token expired.")
            return JSONResponse(
                status_code=401,
                content={"error": "token_expired", "message": "Firebase token expired."}
            )
        except firebase_auth.RevokedIdTokenError:
            logger.warning("Firebase token revoked.")
            return JSONResponse(
                status_code=401,
                content={"error": "token_revoked", "message": "Firebase token revoked."}
            )
        except Exception as exc:
            logger.warning(f"Invalid Firebase token: {exc}")
            return JSONResponse(
                status_code=401,
                content={"error": "token_invalid", "message": "Invalid token."}
            )
