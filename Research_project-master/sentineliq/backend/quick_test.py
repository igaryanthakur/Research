"""quick_test.py — test specific regex patterns against the CEO BEC email"""
import re, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8") # type: ignore

text = (
    "Dear Finance Team, I am currently traveling and unable to access the corporate VPN. "
    "Please expedite the payment of $45,000 to our new vendor listed in the attached invoice "
    "by COB today to avoid late penalties. I will provide formal approval via the system "
    "once my access is restored. Regards, CEO"
)

patterns = {
    "expedite_payment_cob": r"(?i)(expedite|process|complete).{0,200}(payment|transfer|wire).{0,200}(today|immediately|urgent|cob|close\s+of\s+business)",
    "regards_ceo": r"(?i)regards.{0,10}(ceo|cfo|cto|president|director|executive|management)",
    "traveling_invoice": r"(?i)(traveling|travel|out\s+of\s+office|abroad|conference).{0,100}(payment|transfer|wire|vendor|invoice)",
    "new_vendor_payment": r"(?i)(new\s+vendor|new\s+supplier|new\s+bank|new\s+account).{0,100}(payment|transfer|deposit|wire)",
    "late_penalty": r"(?i)(late\s+penalt|late\s+fee|penalt).{0,50}(payment|transfer|invoice)",
    "dollar_amount_today": r"(?i)(wire|transfer|send|pay).{0,30}\$[\d,]+.{0,100}(today|immediately|urgent|asap|cob)",
    "expedite_raw": r"(?i)expedite",
    "payment_raw": r"(?i)payment",
    "today_raw": r"(?i)today",
}

print("Testing against CEO BEC email:")
print("-" * 60)
for name, pattern in patterns.items():
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    status = "MATCH" if m else "NO MATCH"
    snippet = repr(m.group(0)[:60]) if m else ""
    print(f"  {status:10s} | {name:30s} | {snippet}")

print()
# Now test the full heuristic
from engines.phishing import _heuristic_score
result = _heuristic_score(text)
score = result.get('confidence', 0)
print(f"Heuristic score for CEO BEC: {score:.4f}")
print(f"Threat features: {result.get('threat_features', [])}")
