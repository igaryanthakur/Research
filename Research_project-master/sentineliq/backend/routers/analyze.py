import io
import csv
import json
import time
import uuid
import logging
import datetime
from itertools import islice
from typing import Any, Dict, List, Optional

try:
    import fitz  # type: ignore  # pymupdf installs as fitz
except ImportError:
    fitz = None
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, field_validator  # type: ignore[import]

from engines.phishing import detect_phishing  # type: ignore[import]
from engines.url_detector import detect_url  # type: ignore[import]
from engines.prompt_injection import detect_injection  # type: ignore[import]
from engines.anomaly import detect_anomaly  # type: ignore[import]
from engines.email_detector import detect_email_vector  # type: ignore[import]
from xai.gemini_narrator import get_narration  # type: ignore[import]
from scoring.risk_scorer import compute_risk  # type: ignore[import]
from scoring.ensemble import ensemble_vote  # type: ignore[import]
from db.database import get_historical_rate  # type: ignore[import]
from services.firestore_writer import write_incident  # type: ignore[import]

logger = logging.getLogger("sentineliq.analyze")
router = APIRouter()

VALID_THREAT_TYPES = {"phishing", "url", "prompt_injection", "anomaly", "email"}


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic v2 response models
# ─────────────────────────────────────────────────────────────────────────────
class ShapFeature(BaseModel):  # type: ignore[misc]
    feature:   str
    weight:    float
    direction: str = "positive"
    # category distinguishes active attack signals from trust-signal absences.
    # MUST be preserved in serialization — popup uses it for color-coding.
    category:  str = "active_attack_signal"

    model_config = {"extra": "allow"}  # pass-through any future engine fields

    @field_validator("weight")  # type: ignore[misc]
    @classmethod
    def normalise_weight(cls, v: Any) -> float:
        w = float(v)
        return float(int(w * 1_000_000 + 0.5)) / 1_000_000  # avoids round(x, n) Pyrefly bug


class TokenHighlight(BaseModel):  # type: ignore[misc]
    token: str
    score: float

    @field_validator("score")  # type: ignore[misc]
    @classmethod
    def normalise_score(cls, v: Any) -> float:
        w = float(v)
        return float(int(w * 10_000 + 0.5)) / 10_000  # avoids round(x, n) Pyrefly bug


class AnalysisResult(BaseModel):  # type: ignore[misc]
    incident_id: str
    threat_type: str
    verdict: str
    confidence: float
    risk_score: int
    risk_band: str
    shap_features: List[ShapFeature]  # type: ignore[type-arg]
    token_highlights: List[TokenHighlight]  # type: ignore[type-arg]
    explanation: str
    action: str
    narration_mode: str
    processing_time_ms: int
    timestamp: str
    detection_mode: str
    redirect_depth: int
    tier_used: str
    source: str
    browser: str
    extension_version: str

    @field_validator("confidence")  # type: ignore[misc]
    @classmethod
    def normalise_confidence(cls, v: Any) -> float:
        w = float(v)
        return float(int(w * 10_000 + 0.5)) / 10_000  # avoids round(x, n) Pyrefly bug


# ─────────────────────────────────────────────────────────────────────────────
# File extraction helpers
# ─────────────────────────────────────────────────────────────────────────────
def _truncate(text: str, n: int) -> str:
    """Truncate string to n chars — uses islice to avoid Pyrefly list-slice false positive."""
    chars: List[str] = list(str(text))
    return "".join(list(islice(iter(chars), n)))


async def _extract_text(file: Optional[UploadFile], typed_content: str) -> str:  # type: ignore[type-arg]
    """Extract text from uploaded file or return typed_content. File takes priority."""
    if file is None:
        return str(typed_content)

    file_bytes = await file.read()
    fname = str(file.filename or "").lower()

    try:
        if fname.endswith(".pdf"):
            doc = fitz.open(stream=file_bytes, filetype="pdf")  # type: ignore[misc]
            parts = [page.get_text() for page in doc]
            return "\n".join(parts)

        if fname.endswith((".txt", ".eml", ".log")):
            try:
                return file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return file_bytes.decode("latin-1", errors="ignore")

        if fname.endswith(".json"):
            return file_bytes.decode("utf-8")

        if fname.endswith(".csv"):
            return file_bytes.decode("utf-8")

    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("File extraction failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    # Unknown extension — try utf-8 decode
    try:
        return file_bytes.decode("utf-8")
    except Exception:
        return str(typed_content)


async def _parse_session(file: Optional[UploadFile], content: str) -> Dict[str, Any]:  # type: ignore[type-arg]
    """Parse session data for anomaly detection from JSON/CSV file or JSON string."""
    if file is not None:
        file_bytes = await file.read()
        fname = str(file.filename or "").lower()
        if fname.endswith(".json"):
            try:
                data = json.loads(file_bytes.decode("utf-8"))
                return dict(data[0]) if isinstance(data, list) else dict(data)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid JSON session: {exc}")
        if fname.endswith(".csv"):
            try:
                reader = csv.DictReader(io.StringIO(file_bytes.decode("utf-8")))
                rows = list(reader)
                if not rows:
                    raise HTTPException(status_code=400, detail="CSV file is empty.")
                return dict(rows[0])
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid CSV session: {exc}")

    # Try JSON string
    try:
        return dict(json.loads(str(content)))
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Anomaly detection requires JSON session data in content or a .json/.csv file.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic Document Threat Scanner (used for PDF/TXT/EML anomaly analysis)
# ─────────────────────────────────────────────────────────────────────────────
_MALWARE_PATTERNS = [
    # PDF exploit / JavaScript injection
    (r"/JavaScript", "embedded_javascript", 0.90),
    (r"/JS\s*", "embedded_javascript", 0.90),
    (r"/OpenAction", "auto_execute_action", 0.85),
    (r"/AA\s*", "additional_action", 0.80),
    (r"/Launch", "launch_action", 0.92),
    (r"/EmbeddedFile", "embedded_file", 0.75),
    (r"/RichMedia", "richmedia_exploit", 0.70),
    (r"/XFA", "xfa_form", 0.65),
    (r"/AcroForm", "acroform", 0.50),
    # Obfuscated shellcode indicators
    (r"eval\s*\(", "eval_code", 0.85),
    (r"unescape\s*\(", "unescape_code", 0.88),
    (r"String\.fromCharCode", "charcode_obfuscation", 0.82),
    (r"ActiveXObject", "activex_exploit", 0.95),
    (r"WScript\.Shell", "wscript_shell", 0.95),
    (r"cmd\.exe", "cmd_execution", 0.92),
    (r"powershell", "powershell_execution", 0.88),
    (r"Base64\.decode", "base64_payload", 0.75),
    # Suspicious document behaviors
    (r"(document\.write|innerHTML)", "dom_injection", 0.70),
    (r"(urllib|requests\.get|fetch\()", "network_call", 0.65),
    (r"exec\s*\(", "exec_call", 0.80),
    (r"subprocess", "subprocess_call", 0.85),
    (r"os\.system", "system_call", 0.88),
    # Credential harvesting
    (r"(password|passwd|credentials)\s*=", "credential_harvest", 0.72),
    (r"keylog", "keylogger", 0.95),
    # Encrypted payload markers
    (r"\\x[0-9a-fA-F]{2}(\\x[0-9a-fA-F]{2}){8,}", "hex_shellcode", 0.90),
    (r"[A-Za-z0-9+/]{100,}={0,2}", "base64_blob", 0.60),
]


async def _analyze_file_content(file_bytes: bytes, fname: str, text: str, app_state: Any) -> Dict[str, Any]:
    """
    Heuristic Document Threat Scanner + LLM cross-check for file uploads (PDF, TXT, EML, etc.).
    Returns a result dict compatible with detect_anomaly output format.
    """
    import re as _re
    matches: List[Dict[str, Any]] = []
    max_score = 0.0

    # Run heuristic patterns
    for pattern, feature, weight in _MALWARE_PATTERNS:
        if _re.search(pattern, text, _re.IGNORECASE):
            matches.append({"feature": feature.replace("_", " "), "weight": weight, "direction": "positive"})
            if weight > max_score:
                max_score = weight

    # Binary scan for PE header (Windows executable embedded in file)
    if b"MZ" in bytes(list(file_bytes)[:2048]):  # type: ignore[operator]
        matches.append({"feature": "embedded PE executable", "weight": 0.98, "direction": "positive"})
        max_score = max(max_score, 0.98)

    # LLM cross-check for certainty
    gemini_score = 0.0
    if getattr(app_state, "gemini_available", False) and getattr(app_state, "gemini_client", None):
        try:
            import asyncio
            snippet = "".join(list(islice(iter(text), 1500)))
            client = app_state.gemini_client
            prompt = (
                f"You are a threat analyst. Analyse this document content for malicious indicators.\n"
                f"File: {fname}\nContent preview:\n{snippet}\n\n"
                "Respond ONLY with valid JSON: {\"verdict\":\"MALICIOUS\",\"confidence\":0.95,\"reason\":\"...\"}\n"
                "Use MALICIOUS, SUSPICIOUS, or BENIGN as verdict."
            )
            def _call() -> Any:
                return client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            loop = asyncio.get_event_loop()
            resp = await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=5.0)  # type: ignore[arg-type]
            import json as _json
            raw = str(resp.text).strip()
            if raw.startswith("```"):
                import re as _re2
                raw = _re2.sub(r"^```[a-z]*\n?", "", raw)
                raw = _re2.sub(r"\n?```$", "", raw.strip())
            parsed = _json.loads(raw)
            v = str(parsed.get("verdict", "BENIGN")).upper()
            gemini_score = float(parsed.get("confidence", 0.0))
            if v == "BENIGN":
                gemini_score = 0.0
        except Exception as exc:
            logger.debug("Gemini file scan failed (non-fatal): %s", exc)

    final_score = max(max_score, gemini_score)

    if final_score >= 0.75:
        verdict = "MALICIOUS"
    elif final_score >= 0.45:
        verdict = "SUSPICIOUS"
    else:
        verdict = "BENIGN"

    # Build top 5 SHAP-like features sorted by weight
    top_features = sorted(matches, key=lambda x: float(x["weight"]), reverse=True)
    top_features = list(islice(iter(top_features), 5))  # type: ignore[misc]

    return {
        "confidence":    float(int(final_score * 10_000 + 0.5)) / 10_000,  # avoids round() overload
        "verdict":       verdict,
        "shap_features": top_features,
        "mode":          "file_heuristic_gemini",
        "layer_a_score": max_score,
        "layer_b_score": gemini_score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main /analyze endpoint
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/analyze", response_model=AnalysisResult)  # type: ignore[misc]
async def analyze(
    request: Request,
    threat_type: str = Form(...),
    content: str = Form(""),
    semantic_divergence: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),  # type: ignore[assignment]
) -> AnalysisResult:
    """Unified threat analysis endpoint. Routes to correct engine by threat_type."""
    start = time.monotonic()

    # 1. Validate threat_type
    if threat_type not in VALID_THREAT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid threat_type '{threat_type}'. Must be one of: {sorted(VALID_THREAT_TYPES)}",
        )

    if not content.strip() and file is None:
        raise HTTPException(status_code=400, detail="Must provide either content or a file.")

    # 2. Unique incident ID
    year = datetime.datetime.utcnow().year
    suffix = _truncate(str(uuid.uuid4().int), 5)
    incident_id = f"INC-{year}-{suffix}"

    try:
        app_state = request.app.state
        engine_result: Dict[str, Any] = {}
        shap_features_raw: List[Dict[str, Any]] = []
        token_highlights_raw: List[Dict[str, Any]] = []

        # 3. Route to correct engine
        if threat_type == "phishing":
            text = await _extract_text(file, content)
            div_obj = None
            if semantic_divergence:
                try:
                    div_obj = json.loads(semantic_divergence)
                except Exception:
                    pass
            engine_result = await detect_phishing(text, app_state, div_obj)
            token_highlights_raw = list(engine_result.get("token_scores", []))
            shap_features_raw = list(engine_result.get("shap_features", []))

        elif threat_type == "url":
            url_text = await _extract_text(file, content)
            engine_result = await detect_url(url_text.strip(), app_state)
            shap_features_raw = list(engine_result.get("shap_features", []))

        elif threat_type == "prompt_injection":
            text = await _extract_text(file, content)
            escalation_mode = getattr(request.state, "escalation_mode", False)
            engine_result = await detect_injection(text, app_state, session_id, escalation_mode)
            shap_features_raw = list(engine_result.get("shap_features", []))

        elif threat_type == "anomaly":
            # If a non-session file is uploaded (PDF, TXT, EML, etc.) → file content scanner
            _is_file_upload = (
                file is not None
                and not str(file.filename or "").lower().endswith((".json", ".csv"))
            )
            if _is_file_upload and file is not None:
                file_bytes_data = await file.read()
                fname_lower = str(file.filename or "").lower()
                # Decode to text for pattern matching
                try:
                    file_text = file_bytes_data.decode("utf-8", errors="ignore")
                except Exception:
                    file_text = ""
                # Also try PDF text extraction
                if fname_lower.endswith(".pdf"):
                    try:
                        doc = fitz.open(stream=file_bytes_data, filetype="pdf")  # type: ignore[misc]
                        pdf_text = "\n".join(page.get_text() for page in doc)
                        file_text = pdf_text + "\n" + file_text  # combine text + raw stream
                    except Exception:
                        pass
                engine_result = await _analyze_file_content(
                    file_bytes_data, fname_lower, file_text, app_state
                )
            else:
                session = await _parse_session(file, content)
                engine_result = await detect_anomaly(session, app_state)
        elif threat_type == "email":
            try:
                vector = dict(json.loads(str(content)))
            except Exception:
                raise HTTPException(status_code=400, detail="Email threat requires JSON vector in content.")
            engine_result = await detect_email_vector(vector, app_state)
            shap_features_raw = list(engine_result.get("shap_features", []))

        verdict: str = str(engine_result.get("verdict", "BENIGN"))
        conf_raw: float = float(engine_result.get("confidence", 0.0))
        confidence: float = float(int(conf_raw * 10_000 + 0.5)) / 10_000
        engine_mode: str = str(engine_result.get("mode", "unknown"))
        redirect_depth: int = int(engine_result.get("redirect_depth", 0))
        tier_used: str = str(engine_result.get("tier_used", "Tier 2"))

        # 3b. Ensemble vote (single-engine run, so only one result in list)
        ensemble_result = ensemble_vote([
            {"engine": threat_type, "verdict": verdict, "confidence": confidence}
        ])
        escalation_bonus: int = int(ensemble_result.get("escalation_bonus", 0))

        # 4. Risk scoring
        historical_rate: float = await get_historical_rate(threat_type)
        risk_score, risk_band = compute_risk(
            confidence, threat_type, shap_features_raw, historical_rate, verdict,
            escalation_bonus
        )

        # 5. Narration (Email handles its own narration)
        if threat_type == "email" and "explanation" in engine_result:
            narration = {
                "explanation": engine_result.get("explanation", ""),
                "action": engine_result.get("action", ""),
                "narration_mode": engine_result.get("mode", "vector_heuristic_ensemble")
            }
        else:
            snippet = _truncate(str(content), 200)
            narration: Dict[str, str] = await get_narration(  # type: ignore[no-redef]
                threat_type=threat_type,
                verdict=verdict,
                shap_features=shap_features_raw,
                snippet=snippet,
                app_state=app_state,
            )

        processing_time_ms: int = int((time.monotonic() - start) * 1000)
        timestamp: str = datetime.datetime.utcnow().isoformat() + "Z"

        # 6. Build validated Pydantic response
        shap_objs = [ShapFeature(**f) for f in shap_features_raw]  # type: ignore[misc]
        tok_objs = [TokenHighlight(**t) for t in token_highlights_raw]  # type: ignore[misc]

        result: AnalysisResult = AnalysisResult(  # type: ignore[call-arg]
            incident_id=incident_id,  # type: ignore[call-arg]
            threat_type=threat_type,  # type: ignore[call-arg]
            verdict=verdict,  # type: ignore[call-arg]
            confidence=confidence,  # type: ignore[call-arg]
            risk_score=int(risk_score),  # type: ignore[call-arg]
            risk_band=str(risk_band),  # type: ignore[call-arg]
            shap_features=shap_objs,  # type: ignore[call-arg]
            token_highlights=tok_objs,  # type: ignore[call-arg]
            explanation=str(narration.get("explanation", "")),  # type: ignore[call-arg]
            action=str(narration.get("action", "")),  # type: ignore[call-arg]
            narration_mode=str(narration.get("narration_mode", "offline_template")),  # type: ignore[call-arg]
            processing_time_ms=processing_time_ms,  # type: ignore[call-arg]
            timestamp=timestamp,  # type: ignore[call-arg]
            detection_mode=engine_mode,  # type: ignore[call-arg]
            redirect_depth=redirect_depth, # type: ignore[call-arg]
            tier_used=tier_used, # type: ignore[call-arg]
            source=getattr(request.state, "source", "website"),  # type: ignore[call-arg]
            browser="unknown",  # type: ignore[call-arg]
            extension_version=getattr(request.state, "extension_version", ""),  # type: ignore[call-arg]
        )

        # ── PRIVACY: Firestore write intentionally removed from backend ──────────
        # Incidents are written exclusively by the authenticated frontend under
        # users/{uid}/incidents/{id} — enforced by Firestore security rules.
        # The backend never touches user history; this is the privacy guarantee.
        # (Exception: backend now writes extension-initiated scans since extension has no SDK)
        await write_incident(
            uid=getattr(request.state, "uid", None),
            engine_result=result.model_dump(),
            threat_type=threat_type,
            extension_version=getattr(request.state, "extension_version", ""),
            source=getattr(request.state, "source", "website")
        )

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unhandled error in /analyze: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal analysis error — check server logs.")
