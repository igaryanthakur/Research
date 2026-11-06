"""
diagnose.py — Per-case diagnostic for anomaly + phishing engines.
Run: venv/Scripts/python.exe -X utf8 diagnose.py
"""
import sys, os, asyncio

print("========================================")
print(" SentinelIQ Diagnostic Script")
print("========================================")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8") # type: ignore

os.environ["TOKENIZERS_PARALLELISM"] = "false"
from unittest.mock import MagicMock

from engines.anomaly import load_anomaly_model, detect_anomaly
from engines.phishing import load_phishing_model, detect_phishing

ANOMALY_CASES = [
    ({"hour": 3,  "day_of_week": 6, "login_velocity": 25, "failed_ratio": 0.90,
      "location_delta_km": 8000, "device_match_int": 0, "session_duration_sec": 10,
      "privilege_escalation_int": 1}, 1, "heavy anomaly"),
    ({"hour": 2,  "day_of_week": 5, "login_velocity": 18, "failed_ratio": 0.80,
      "location_delta_km": 5000, "device_match_int": 0, "session_duration_sec": 20,
      "privilege_escalation_int": 1}, 1, "heavy anomaly 2"),
    ({"hour": 1,  "day_of_week": 6, "login_velocity": 15, "failed_ratio": 0.75,
      "location_delta_km": 3000, "device_match_int": 0, "session_duration_sec": 15,
      "privilege_escalation_int": 1}, 1, "heavy anomaly 3"),
    ({"hour": 9,  "day_of_week": 1, "login_velocity": 1, "failed_ratio": 0.00,
      "location_delta_km": 3, "device_match_int": 1, "session_duration_sec": 900,
      "privilege_escalation_int": 0}, 0, "normal 9am"),
    ({"user_role": "developer", "hour": 3, "day_of_week": 5, "login_velocity": 2,
      "failed_ratio": 0.0, "location_delta_km": 0, "device_match_int": 1,
      "session_duration_sec": 14000, "privilege_escalation_int": 0}, 0, "dev nightshift"),
    ({"hour": 14, "day_of_week": 3, "login_velocity": 2, "failed_ratio": 0.05,
      "location_delta_km": 8, "device_match_int": 1, "session_duration_sec": 1200,
      "privilege_escalation_int": 0}, 0, "normal 2pm"),
    ({"hour": 11, "day_of_week": 2, "login_velocity": 1, "failed_ratio": 0.02,
      "location_delta_km": 5, "device_match_int": 1, "session_duration_sec": 600,
      "privilege_escalation_int": 0}, 0, "normal 11am"),
]

PHISHING_FAIL = (
    "Dear Finance Team, I am currently traveling and unable to access the corporate VPN. "
    "Please expedite the payment of $45,000 to our new vendor listed in the attached invoice "
    "by COB today to avoid late penalties. I will provide formal approval via the system "
    "once my access is restored. Regards, CEO",
    1, "LLM CEO BEC"
)

async def main():
    app = MagicMock()
    app.state = MagicMock()
    app.state.gemini_available = False  # offline mode

    print("=" * 60)
    print("  ANOMALY ENGINE DIAGNOSTIC")
    print("=" * 60)
    await load_anomaly_model(app)

    anomaly_pass = 0
    for case, expected, label in ANOMALY_CASES:
        r = await detect_anomaly(case, app.state)
        pred = 1 if r["verdict"] in ("MALICIOUS", "SUSPICIOUS") else 0
        ok = pred == expected
        if ok:
            anomaly_pass += 1
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] expected={expected} got={r['verdict']:10s} conf={r['confidence']:.4f} | {label}")

    print(f"\n  Anomaly: {anomaly_pass}/{len(ANOMALY_CASES)} passed\n")

    print("=" * 60)
    print("  PHISHING ENGINE DIAGNOSTIC (offline — no Gemini)")
    print("=" * 60)
    await load_phishing_model(app)
    text, expected, label = PHISHING_FAIL
    r = await detect_phishing(text, app.state)
    pred = 1 if r["verdict"] in ("MALICIOUS", "SUSPICIOUS") else 0
    ok = pred == expected
    print(f"  [{'OK  ' if ok else 'FAIL'}] expected={expected} got={r['verdict']:10s} conf={r['confidence']:.4f} heuristic_signals_present")
    print(f"  mode: {r['mode']}")

asyncio.run(main())
