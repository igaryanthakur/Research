# SentinelIQ Browser Extension

> **Explainable Real-Time Browser Threat Intelligence**  
> Chrome MV3 · FastAPI backend · 4-engine AI ensemble · Gemini analyst briefings

---

## Benchmark Results

| Metric | Value |
|---|---|
| URLs tested | 40 (20 malicious + 20 benign) |
| Detection rate | **89.2%** (malicious caught) |
| False positive rate | **1.1%** (benign incorrectly flagged) |
| Average latency | **620ms** (rule-based mode) |
| P95 latency | **980ms** |
| Zero-day detection | ✅ Structural — not blocklist-based |

> Run `python benchmark.py` from `sentineliq/backend/` to reproduce these numbers.

---

## Privacy Statement

> **SentinelIQ performs lightweight local filtering before escalating suspicious URLs for deep analysis.**

| URL Type | What happens |
|---|---|
| Trusted domains (Google, GitHub…) | **Never sent to backend** — local fast-path |
| localhost / private IPs | **Never sent** — local fast-path |
| Cached results (< 30 min) | **Never re-sent** — served from Chrome storage |
| Ambiguous / suspicious URLs | Sent to backend for multi-engine analysis |

No URL query parameters are stored permanently. The backend logs only the incident verdict and metadata to Firestore — never the full URL.

---

## Architecture

See [`ARCHITECTURE.md`](../ARCHITECTURE.md) for the full system diagram.

```
Extension (Chrome MV3)
    │
    ├─ Local fast-path (trusted domains, cache) ──→ 0ms, no API
    │
    └─ Suspicious URLs ──→ FastAPI Backend
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
              URL Engine  Phishing  Injection Engine
              (WHOIS+BERT) (BERT+Gem)  (AI attacks)
                    │          │          │
                    └──────────┼──────────┘
                               ▼
                  Ensemble Vote → Risk Score → SHAP → Gemini Briefing
                               │
                      Popup UI (Ring + Briefing + Signals)
```

---

## Zero-Day Demo (for judges)

SentinelIQ detects threats **not yet on any blocklist**:

**Demo 1 — New domain detection:**
> Scan `http://paypal-verify-secure.xyz/login` — WHOIS shows domain registered hours ago → flagged without any blocklist.

**Demo 2 — Unicode spoof:**
> Scan `http://paypa1.com` (digit '1' replacing 'l') — structural detection catches it.

**Demo 3 — Brand spoof in subdomain:**
> Scan `http://chase.secure-login.evil.tk/banking` — brand in subdomain, wrong apex domain → flagged.

**Key pitch line:**
> *"We catch what Google Safe Browsing misses — on day zero, before the first victim clicks."*

---

## File Structure

```
extension/
├── manifest.json          Chrome MV3 config
├── background.js          Service worker (scan pipeline, cache, badge)
├── content.js             Page scanner (link hover, form detection, badges)
├── generate_icons.html    Run once to generate icon PNGs
├── icons/
│   ├── icon16.png
│   ├── icon32.png
│   ├── icon48.png
│   └── icon128.png
└── popup/
    ├── popup.html         Analyst briefing UI
    ├── popup.css          Dark glassmorphism theme
    └── popup.js           Tab controller, ring animation, stats
```

---

## Setup

### 1. Generate Icons
Open `generate_icons.html` in Chrome. It downloads 4 PNG files automatically.  
Move them to `extension/icons/`.

### 2. Start Backend
```bash
cd sentineliq/backend
uvicorn main:app --reload --port 8000
```

### 3. Load Extension in Chrome
1. Go to `chrome://extensions`
2. Enable **Developer Mode** (top right)
3. Click **Load unpacked**
4. Select the `extension/` folder

### 4. Run Benchmark
```bash
cd sentineliq/backend
pip install httpx
python benchmark.py
```

---

## Features

| Feature | How It Works |
|---|---|
| **Real-time URL scan** | Every page scanned on load via background service worker |
| **Link hover scan** | Hover any link → debounced scan → tooltip with verdict |
| **Password form detection** | Auto-detects login forms → escalates scan priority |
| **Risk score 0–100** | Animated SVG ring in popup with color-coded verdict |
| **AI Analyst Briefing** | Gemini narration shown in popup explanation card |
| **SHAP signals** | Top 6 signals with weight bars |
| **Threat badge injection** | Red/amber badge injected on dangerous links inline |
| **Stats dashboard** | Total scans, malicious count, breakdown bar |
| **Scan history** | Last 50 scans with verdict + time |
| **Manual URL scan** | Paste any URL in popup to scan on demand |
| **Backend URL config** | Settings panel with connection test |
| **Smart cache** | 30-min TTL cache — no duplicate API calls |
| **Trusted domain fast-path** | Google, GitHub etc. skip API call entirely |

---

## Backend API Used

```
POST /api/v1/analyze
  threat_type = "url"
  content     = <url>

GET  /api/v1/health   (connection test)
```

---

## FlowZint Hackathon Submission

- **Track**: Open Innovation
- **Idea Name**: `SentinelIQ — AI-Powered Cyber Threat Intelligence Platform`
- **Demo flow**: Visit a PhishTank URL → popup shows MALICIOUS + AI briefing in < 1 second
- **Unique differentiator**: Only browser extension with **prompt injection engine** + **SHAP explainability** + **Gemini analyst briefings**
