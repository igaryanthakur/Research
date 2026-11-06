import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import logging
logging.basicConfig(level=logging.WARNING)

from test_accuracy import EMAIL_CASES, _run_email, _metrics, _print_result
from unittest.mock import MagicMock
from engines.phishing import load_phishing_model

async def run_only_email():
    app = MagicMock()
    app.state = MagicMock()
    
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and not api_key.startswith("="):
        from google import genai
        app.state.gemini_available = True
        app.state.gemini_client = genai.Client(api_key=api_key)
    else:
        app.state.gemini_available = False
        app.state.gemini_client = None

    await load_phishing_model(app)
    
    print("Running Email tests...")
    yt, yp, yprob = await _run_email(app.state)
    m = _metrics(yt, yp, yprob)
    _print_result("Email", m, len(EMAIL_CASES))

if __name__ == "__main__":
    asyncio.run(run_only_email())
