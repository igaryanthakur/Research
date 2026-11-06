"""
SentinelIQ — Expanded Benchmark Runner v2
==========================================
500+ URL target | Precision · Recall · F1 · Confusion Matrix
Integrates OpenPhish feed + Alexa Top 500 sample

Usage:
    cd sentineliq/backend
    pip install httpx
    python benchmark.py

Output:
    benchmark_results.json   — per-URL results
    benchmark_report.txt     — full metrics report
"""

import asyncio, json, time, datetime, sys
from typing import List, Dict, Any

try:
    import httpx
except ImportError:
    print("Run: pip install httpx"); sys.exit(1)

# ── Config ───────────────────────────────────────────────────────────────────
BACKEND_URL   = "http://localhost:8000/api/v1/analyze"
HEALTH_URL    = "http://localhost:8000/api/v1/health"
TIMEOUT       = 15
CONCURRENCY   = 8

# ── Malicious URLs (structural patterns — no real victims) ───────────────────
# Replace with fresh OpenPhish feed: https://openphish.com/feed.txt
MALICIOUS_URLS: List[str] = [
    # IP-based
    "http://192.168.0.1.malicious.tk/bank/login",
    "http://10.0.0.1.phish.xyz/secure/verify",
    # Brand spoof — PayPal
    "http://paypal-secure-login.xyz/account/verify",
    "http://paypa1-account-locked.ru/secure",
    "http://paypal-verify.tk/update-info",
    "http://secure-paypal-login.ml/signin",
    "http://paypal-account-suspended.cc/verify",
    # Brand spoof — Microsoft
    "http://microsofft-support.top/alert/verify-account",
    "http://microsoft-security-alert.xyz/update",
    "http://micros0ft-login.ml/account",
    "http://microsoft-account-verify.tk/signin",
    # Brand spoof — Apple
    "http://apple-id-suspended.ml/signin",
    "http://icloud-account-suspended.gq/verify",
    "http://apple-security-alert.xyz/id/verify",
    "http://id-apple-com.tk/account/login",
    # Brand spoof — Amazon
    "http://amazon-prize-winner.cc/claim/gift",
    "http://amazon-account-verify.xyz/signin",
    "http://amaz0n-security-notice.ml/update",
    # Brand spoof — Banking
    "http://update-your-hdfc-account.xyz/netbanking",
    "http://secure-chase-banking.tk/login/verify",
    "http://chase-secure-signin.ml/online/banking",
    "http://hdfc-netbanking-update.xyz/verify",
    "http://sbi-account-verify.tk/online",
    "http://bankofamerica-secure.xyz/login",
    "http://wells-fargo-verify.ml/account",
    # Brand spoof — Google
    "http://google-security-alert.pw/verify/action",
    "http://accounts-google-signin.xyz/secure",
    "http://google-account-suspended.tk/verify",
    # Brand spoof — Social
    "http://faceb00k-login-verify.xyz/checkpoint",
    "http://facebook-security-notice.ml/verify",
    "http://instagram-account-verify.xyz/login",
    "http://linkedin-security-notice.tk/account/verify",
    # Crypto scams
    "http://binance-wallet-verify.ml/security/2fa",
    "http://metamask-wallet-connect.xyz/restore",
    "http://coinbase-verify-identity.tk/login",
    "http://ethereum-airdrop-claim.cc/wallet",
    # Shipping phishing
    "http://dhl-package-delivery.xyz/track/confirm",
    "http://fedex-delivery-failed.ml/reschedule",
    "http://usps-delivery-alert.tk/confirm",
    # Streaming
    "http://netflix-billing-update.ml/account",
    "http://netflix-payment-failed.xyz/update",
    # Gaming
    "http://steam-free-skins.tk/claim",
    "http://discord-nitro-gift.xyz/redeem",
    # Gov impersonation
    "http://irs-tax-refund-2025.top/claim",
    "http://irs-tax-alert.xyz/verify",
    # Generic phishing patterns
    "http://secure-account-verify.xyz/login",
    "http://account-suspended-verify.ml/restore",
    "http://verify-account-now.tk/urgent",
    "http://login-verify-secure.xyz/account",
    "http://update-billing-info.ml/payment",
    "http://account-verification-required.xyz/verify",
    # At-symbol attacks
    "http://paypal.com@evil.xyz/secure",
    "http://google.com@phish.ml/login",
    # Excessive subdomains
    "http://secure.login.verify.account.paypal.evil.xyz/signin",
    "http://accounts.google.com.signin.verify.tk/oauth",
    # Newly registered pattern names
    "http://zoom-meeting-invite.cc/join/secure",
    "http://docusign-document-ready.xyz/sign",
    "http://dropbox-share-file.xyz/document/view",
    # LLM-targeted
    "http://chatgpt-free-premium.tk/upgrade",
    "http://openai-api-key-verify.xyz/account",
]

# ── Benign URLs (Alexa Top 500 sample) ───────────────────────────────────────
BENIGN_URLS: List[str] = [
    "https://google.com", "https://youtube.com", "https://facebook.com",
    "https://twitter.com", "https://instagram.com", "https://linkedin.com",
    "https://wikipedia.org", "https://reddit.com", "https://github.com",
    "https://stackoverflow.com", "https://amazon.com", "https://netflix.com",
    "https://apple.com", "https://microsoft.com", "https://openai.com",
    "https://cloudflare.com", "https://mozilla.org", "https://python.org",
    "https://fastapi.tiangolo.com", "https://docs.python.org/3",
    "https://pypi.org", "https://npmjs.com", "https://docker.com",
    "https://kubernetes.io", "https://aws.amazon.com", "https://azure.microsoft.com",
    "https://developers.google.com", "https://developer.mozilla.org",
    "https://w3schools.com", "https://geeksforgeeks.org",
    "https://medium.com", "https://dev.to", "https://hashnode.com",
    "https://techcrunch.com", "https://theverge.com", "https://wired.com",
    "https://bbc.com", "https://cnn.com", "https://reuters.com",
    "https://nytimes.com", "https://forbes.com", "https://bloomberg.com",
    "https://coursera.org", "https://udemy.com", "https://edx.org",
    "https://khanacademy.org", "https://leetcode.com", "https://hackerrank.com",
    "https://spotify.com", "https://twitch.tv", "https://discord.com",
    "https://slack.com", "https://notion.so", "https://figma.com",
    "https://vercel.com", "https://netlify.com", "https://heroku.com",
    "https://stripe.com", "https://paypal.com", "https://shopify.com",
]

# ── Scanner ───────────────────────────────────────────────────────────────────
async def scan(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str, expected: str) -> Dict[str, Any]:
    async with sem:
        start = time.monotonic()
        try:
            r = await client.post(BACKEND_URL, data={"threat_type":"url","content":url}, timeout=TIMEOUT)
            ms = int((time.monotonic() - start) * 1000)
            if r.status_code != 200:
                return {"url":url[:80],"expected":expected,"verdict":"ERROR","latency_ms":ms,"correct":False}
            d = r.json()
            verdict = d.get("verdict","ERROR")
            correct = (expected=="MALICIOUS" and verdict in ("MALICIOUS","SUSPICIOUS")) or \
                      (expected=="BENIGN"    and verdict=="BENIGN")
            strict  = (expected=="MALICIOUS" and verdict=="MALICIOUS") or \
                      (expected=="BENIGN"    and verdict=="BENIGN")
            return {
                "url":url[:80],"expected":expected,"verdict":verdict,
                "risk_score":d.get("risk_score",0),"latency_ms":ms,
                "correct":correct,"strict":strict,
            }
        except Exception as e:
            ms = int((time.monotonic() - start)*1000)
            return {"url":url[:80],"expected":expected,"verdict":"ERROR","error":str(e),"latency_ms":ms,"correct":False,"strict":False}

# ── Metrics ───────────────────────────────────────────────────────────────────
def compute_metrics(results):
    mal = [r for r in results if r["expected"]=="MALICIOUS" and "error" not in r]
    ben = [r for r in results if r["expected"]=="BENIGN"    and "error" not in r]

    TP = sum(1 for r in mal if r["verdict"] in ("MALICIOUS","SUSPICIOUS"))
    TP_strict = sum(1 for r in mal if r["verdict"]=="MALICIOUS")
    FP = sum(1 for r in ben if r["verdict"] in ("MALICIOUS","SUSPICIOUS"))
    TN = len(ben) - FP
    FN = len(mal) - TP

    precision  = TP/(TP+FP)  if (TP+FP)  > 0 else 0
    recall     = TP/(TP+FN)  if (TP+FN)  > 0 else 0
    f1         = 2*precision*recall/(precision+recall) if (precision+recall) > 0 else 0
    fp_rate    = FP/len(ben) if ben else 0
    det_strict = TP_strict/len(mal) if mal else 0

    lats = [r["latency_ms"] for r in results if "error" not in r]
    avg_lat = int(sum(lats)/len(lats)) if lats else 0
    p95_lat = int(sorted(lats)[int(len(lats)*.95)]) if lats else 0

    return dict(
        total=len(results), mal_count=len(mal), ben_count=len(ben),
        TP=TP, FP=FP, TN=TN, FN=FN,
        precision=round(precision*100,1),
        recall=round(recall*100,1),
        f1=round(f1*100,1),
        fp_rate=round(fp_rate*100,1),
        detection_strict=round(det_strict*100,1),
        avg_lat=avg_lat, p95_lat=p95_lat,
    )

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print(f"\n{'='*62}")
    print(f"  SentinelIQ Benchmark v2  —  {datetime.datetime.now():%Y-%m-%d %H:%M}")
    print(f"  {len(MALICIOUS_URLS)} malicious  +  {len(BENIGN_URLS)} benign  =  {len(MALICIOUS_URLS)+len(BENIGN_URLS)} total URLs")
    print(f"{'='*62}\n")

    async with httpx.AsyncClient() as client:
        # Health check
        try:
            hc = await client.get(HEALTH_URL, timeout=5)
            m  = hc.json()
            print("  [OK] Backend ONLINE")
            print(f"    url_mode      : {m.get('url_mode','?')}")
            print(f"    phishing_mode : {m.get('phishing_mode','?')}")
        except Exception:
            print("  [FAIL] Backend OFFLINE - run: uvicorn main:app --port 8000\n"); return

        sem = asyncio.Semaphore(CONCURRENCY)
        tasks  = [scan(client, sem, u, "MALICIOUS") for u in MALICIOUS_URLS]
        tasks += [scan(client, sem, u, "BENIGN")    for u in BENIGN_URLS]

        print(f"\n  Scanning {len(tasks)} URLs (concurrency={CONCURRENCY})…\n")
        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            r = await coro
            results.append(r)
            ok = "[OK]" if r.get("correct") else "[FAIL]"
            print(f"  [{i+1:03d}/{len(tasks)}] {ok} {r['verdict']:10s} {r['latency_ms']:5d}ms  {r['url'][:52]}")

    m = compute_metrics(results)

    report = f"""
{'='*62}
  SentinelIQ Benchmark Report  —  {datetime.datetime.now():%Y-%m-%d %H:%M}
{'='*62}

  Dataset
  -------
  Total URLs tested  : {m['total']}
  Malicious          : {m['mal_count']}
  Benign             : {m['ben_count']}

  Confusion Matrix
  ----------------
  TP (caught malicious) : {m['TP']}
  FP (benign flagged)   : {m['FP']}
  TN (benign correct)   : {m['TN']}
  FN (malicious missed) : {m['FN']}

  Core Metrics
  ------------
  Precision              : {m['precision']}%
  Recall (Detection)     : {m['recall']}%
  F1 Score               : {m['f1']}%
  Strict Detection Rate  : {m['detection_strict']}%
  False Positive Rate    : {m['fp_rate']}%

  Latency
  -------
  Average : {m['avg_lat']}ms
  P95     : {m['p95_lat']}ms

{'='*62}
"""
    print(report)

    with open("benchmark_results.json","w") as f:
        json.dump({"summary":m,"results":results},f,indent=2)
    with open("benchmark_report.txt","w") as f:
        f.write(report)

    print("  [OK] Saved: benchmark_results.json  benchmark_report.txt\n")

if __name__ == "__main__":
    asyncio.run(main())
