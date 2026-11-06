import sys, os, asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["TOKENIZERS_PARALLELISM"] = "false"
from unittest.mock import MagicMock
from engines.url_detector import load_url_model, detect_url
from test_accuracy import URL_CASES

async def main():
    app = MagicMock()
    app.state = MagicMock()
    await load_url_model(app)

    print("========================================")
    print(" URL FALSE NEGATIVES DIAGNOSTIC")
    print("========================================")

    for url, expected in URL_CASES:
        if expected == 1:
            res = await detect_url(url, app.state)
            pred = 1 if res["verdict"] in ("MALICIOUS", "SUSPICIOUS") else 0
            if pred != expected:
                print(f"[FALSE NEGATIVE] URL: {url}")
                print(f"  Score: {res['confidence']:.4f} | Verdict: {res['verdict']}")
                features = [f"{f['feature']} ({f['weight']})" for f in res.get('shap_features', [])]
                print(f"  Triggered Features: {features}")
                print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
