import asyncio
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)

class MockApp:
    class State:
        phishing_model = None
        phishing_mode = 'heuristic_fallback'
        gemini_available = False
    
    state = State()

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import PhishingConfig
from engines.phishing import detect_phishing

test_cases = [
    ('Dear User, verify immediately. Within 24 hours your account will be locked. [Verify Now]',
     'MALICIOUS', 'Should be CRITICAL — was giving 5%'),

    ('Your account has been suspended. Confirm your identity within 24 hours or lose access.',
     'MALICIOUS', 'Account suspension + 24hr deadline'),

    ('Urgent: We noticed unusual activity. Verify your account now to prevent it from being closed.',
     'MALICIOUS', 'Urgency + account threat'),

    ('Hi Sarah, just confirming our 3pm meeting tomorrow. Let me know if that works.',
     'BENIGN', 'Normal email — no signals'),
]

async def run():
    print('Starting tests...')
    for text, expected, note in test_cases:
        result = await detect_phishing(text, MockApp.state)
        status = '✓ PASS' if result['verdict'] == expected else f'✗ FAIL (Expected {expected}, Got {result["verdict"]})'
        print(f'\n{status} | {note}')
        print(f'  Input:      {text[:60]}...')
        print(f'  Got:        {result["verdict"]} ({result["confidence"]:.0%})')
        print(f'  Triggered:  {result.get("triggered_signals", [])}')

if __name__ == '__main__':
    asyncio.run(run())
