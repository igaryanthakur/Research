import os

# Force CPU only — set before any torch/transformers import
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request  # type: ignore[import]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[import]
from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()

# Set HuggingFace token if provided in .env — enables private/restricted model downloads
_hf_token = os.getenv("HUGGINGFACE_TOKEN", "").strip()
if _hf_token:
    os.environ["HUGGING_FACE_HUB_TOKEN"] = _hf_token
    os.environ["HF_TOKEN"] = _hf_token


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)
logger = logging.getLogger("sentineliq")

from routers import analyze, incidents  # type: ignore[import]
from engines.phishing import load_phishing_model  # type: ignore[import]
from engines.url_detector import load_url_model, _WHOIS_EXECUTOR  # type: ignore[import]
from engines.prompt_injection import compile_patterns  # type: ignore[import]
from engines.anomaly import load_anomaly_model  # type: ignore[import]
from db.database import init_firebase  # type: ignore[import]
from config import validate_config  # type: ignore[import]
from middleware.auth_middleware import AuthMiddleware  # type: ignore[import]

async def init_featherless(app: FastAPI) -> None:
    api_key = os.getenv("FEATHERLESS_API_KEY", "").strip()
    if api_key:
        try:
            from openai import AsyncOpenAI  # type: ignore[import]
            app.state.gemini_client = AsyncOpenAI(
                base_url="https://api.featherless.ai/v1",
                api_key=api_key
            )
            app.state.gemini_available = True
            logger.info("Featherless client initialized.")
        except Exception as exc:
            app.state.gemini_client = None
            app.state.gemini_available = False
            logger.error("Failed to init Featherless client: %s", exc)
    else:
        app.state.gemini_client = None
        app.state.gemini_available = False
        logger.warning("FEATHERLESS_API_KEY not set - offline mode only.")



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("\u2501" * 50)
    logger.info("  SentinelIQ \u2014 Starting up")
    logger.info("\u2501" * 50)

    # Validate config FIRST — after logging is configured, not at import time.
    # This logs GSB API key presence, Gemini key, etc.
    validate_config()

    await init_firebase(app)
    await load_phishing_model(app)
    await load_url_model(app)
    await compile_patterns(app)
    await load_anomaly_model(app)
    await init_featherless(app)

    logger.info("\u2501" * 50)
    logger.info(f"  phishing  \u2192 {app.state.phishing_mode}")
    logger.info(f"  url       \u2192 {app.state.url_mode}")
    logger.info(f"  injection \u2192 {app.state.injection_mode}")
    logger.info(f"  anomaly   \u2192 {app.state.anomaly_mode}")
    logger.info(f"  firebase  \u2192 {app.state.firebase_mode}")
    logger.info("  SentinelIQ ready.")
    logger.info("\u2501" * 50)

    yield  # app runs here

    logger.info("SentinelIQ shutting down.")
    # Gracefully shut down the WHOIS ThreadPoolExecutor so in-flight queries
    # are allowed to complete rather than being abandoned mid-WHOIS lookup.
    _WHOIS_EXECUTOR.shutdown(wait=True)
    logger.info("WHOIS executor shut down cleanly.")


app = FastAPI(
    title="SentinelIQ API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

app.include_router(analyze.router, prefix="/api/v1")
app.include_router(incidents.router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/v1/health")
async def health(request: Request):
    return {
        "status": "ok",
        "phishing_mode": getattr(request.app.state, "phishing_mode", "unknown"),
        "url_mode": getattr(request.app.state, "url_mode", "unknown"),
        "injection_mode": getattr(request.app.state, "injection_mode", "unknown"),
        "anomaly_mode": getattr(request.app.state, "anomaly_mode", "unknown"),
        "firebase_mode": getattr(request.app.state, "firebase_mode", "unknown"),
    }
