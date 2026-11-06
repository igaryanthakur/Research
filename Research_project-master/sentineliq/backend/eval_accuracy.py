import asyncio
from engines.phishing import detect_phishing
from engines.url_detector import detect_url

# Test Cases
PHISHING_SAMPLES = {
    "Generic Account Lock (No Brand)": (
        "Dear User, your account profile access has been restricted due to suspicious activity. "
        "Failure to respond within 24 hours will lead to termination of your access. "
        "Please click the secure link below to re-verify your identity."
    ),
    "CEO Wire Transfer (BEC)": (
        "Dear Finance Team, I am currently traveling and unable to access the corporate VPN. "
        "Please expedite the payment of $45,000 to our new vendor listed in the attached invoice "
        "by COB today to avoid late penalties. I will provide formal approval via the system "
        "once my access is restored. Regards, CEO"
    ),
    "Benign Business Email": (
        "Hi team, just a quick reminder that the quarterly all-hands meeting is scheduled for "
        "tomorrow at 10 AM in the main conference room. Please review the attached agenda. "
        "Thanks, HR"
    )
}

URL_SAMPLES = {
    "Deceptive Subdomain (Generic)": "https://secure-login.update-account.com.attacker.xyz/login",
    "Keyword Stacking (No Brand)": "https://example.com/verify/account/secure/login/authenticate",
    "Numeric Abuse": "https://192.168.1.100/reset-password",
    "Benign Tech Blog": "https://blog.developer.com/new-react-features-2026/"
}

async def run_eval():
    print("=== PHISHING ENGINE EVALUATION (GENERIC SIGNALS) ===")
    for name, text in PHISHING_SAMPLES.items():
        result = await detect_phishing(text, None)
        conf = result.get('confidence', 0) * 100
        threats = [f['feature'] for f in result.get('shap_features', [])]
        print(f"\n[{name}]")
        print(f"Risk Confidence: {conf:.1f}%")
        print(f"Threat Features Triggered: {threats if threats else 'None'}")

    print("\n\n=== URL ENGINE EVALUATION (STRUCTURAL SIGNALS) ===")
    for name, url in URL_SAMPLES.items():
        result = await detect_url(url, None)
        conf = result.get('confidence', 0) * 100
        threats = [f['feature'] for f in result.get('shap_features', [])]
        print(f"\n[{name}]")
        print(f"Risk Confidence: {conf:.1f}%")
        print(f"Threat Features Triggered: {threats if threats else 'None'}")

if __name__ == "__main__":
    asyncio.run(run_eval())
