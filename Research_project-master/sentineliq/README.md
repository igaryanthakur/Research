<div align="center">
  <img src="assets/logo.png" alt="SentinelIQ Logo" width="150" style="border-radius: 20px; margin-bottom: 20px;" />
  <h1>SentinelIQ</h1>
  <p><b>Explainable Real-Time Browser Threat Intelligence</b></p>
  
  [![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![Node.js 18+](https://img.shields.io/badge/Node.js-18+-339933?style=for-the-badge&logo=nodedotjs&logoColor=white)](https://nodejs.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
  [![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://reactjs.org/)
  
  <p>
    An advanced, privacy-first threat detection ecosystem featuring a 4-engine ensemble, zero-day threat prevention, and real-time Explainable AI (XAI) insights.
  </p>
</div>

---

## 🌟 Product Overview

**SentinelIQ** is a zero-latency, highly optimized browser extension and backend ecosystem designed to intercept zero-day phishing, malicious URLs, prompt injections, and behavioral anomalies. Unlike traditional blocklists, SentinelIQ leverages a robust 4-Engine Ensemble and state-of-the-art XAI to not just block threats, but **explain why** they were flagged, offering unparalleled transparency and actionable intelligence.

### 🛡️ Core Capabilities

- **Zero-Day Detection**: Catches threats before they appear on blocklists using WHOIS domain age, DOM scraping, and brand spoof rules.
- **4-Engine Ensemble Architecture**: Combines Phishing, URL, Prompt Injection, and Anomaly engines for high-confidence verdicts.
- **Explainable AI (XAI)**: Demystifies AI decisions with SHAP feature attributions and Token highlights.
- **Privacy-First Fast Path**: Local trusted domain checks and caching ensure complete privacy for non-malicious browsing.

---

## 🏆 Evaluation Alignment

**1. Model Innovation & Novelty (30%)**
SentinelIQ moves beyond binary blocklists by deploying a **4-Engine AI Ensemble** directly interacting with the browser's DOM. Our most novel contribution is the real-time **Explainable AI (XAI) pipeline**, which generates dynamic SHAP-based rationales and Analyst Briefings for the end-user, transforming an opaque "block" into a transparent educational moment.

**2. Real-World Applicability (25%)**
We target the most damaging modern threat vectors:
- **Zero-Day Phishing & HTML Smuggling**: By parsing live DOM content and local `file://` execution, we catch active credential harvesters before they are reported to traditional blocklists.
- **Business Email Compromise (BEC)**: Deep content scanning detects urgency language and brand impersonation in webmail clients.

**3. Technical Architecture (25%)**
The system is built for resilience and zero-latency browsing:
- **Privacy Fast-Path**: O(1) local cache lookups and Private IP exemptions ensure safe traffic never hits the cloud.
- **Robust State Management**: Service worker architecture includes exponential backoff retries, ensuring the extension recovers gracefully from cloud backend cold-starts without hanging the UI.
- **Separation of Concerns**: Pure JavaScript extension interacts via REST with a stateless, scalable FastAPI Python backend.

**4. Documentation Clarity (20%)**
This repository provides comprehensive setup instructions, explicit architectural diagrams, environment variable schemas, and API documentation to ensure seamless onboarding and review.

---

## 🏗️ System Architecture

Our highly optimized pipeline operates on a lightweight local filtering model before escalating suspicious URLs for deep analysis, guaranteeing minimal latency for safe domains.

```mermaid
flowchart TD
    %% Browser & Extension
    Browser["🌐 Browser (Chrome)"] --> ExtLayer

    subgraph ExtLayer["🧩 Extension Layer"]
        direction TB
        Content["content.js\n(Hover & Forms)"]
        Background["background.js\n(Service Worker)"]
        Popup["popup.html\n(Risk Dashboard)"]
        Content -->|"Signals"| Background
    end

    %% Local Fast Path
    Background -->|"Validate"| FastPath
    subgraph FastPath["⚡ Local Fast-Path"]
        direction TB
        Trusted["✓ Trusted Domains"]
        LocalIP["✓ Localhost / Private IPs"]
        Cache["✓ Local Cache (30m TTL)"]
    end

    %% API / Backend
    FastPath -->|"Miss → Escalate"| API
    subgraph API["🧠 FastAPI Backend (4-Engine Ensemble)"]
        direction TB
        Router["Router (/api/v1/analyze)"]
        
        Router --> Engines
        subgraph Engines["AI Threat Engines"]
            direction LR
            URL["🔗 URL Engine\n(Heuristics, WHOIS)"]
            Phish["📧 Phishing Engine\n(Heuristics, Gemini)"]
            Inject["🤖 Injection Engine\n(Pattern Match)"]
            Anomaly["📊 Anomaly Engine\n(Isolation Forest)"]
        end

        Engines --> Voter["⚖️ Ensemble Voter\n(Detection Consensus)"]
        Voter --> Risk["🎯 Risk Scorer\n(Prioritization)"]
        Risk --> XAI["🔍 Explainable AI (SHAP)"]
        XAI --> Narrator["💬 Gemini Narrator\n(Analyst Briefings)"]
    end

    %% Return Path
    Narrator -->|"JSON Response"| Background
    Background --> Popup
```

---

## ⚠️ System Limitations & Future Work
*SentinelIQ is a functional prototype demonstrating defense-in-depth principles. It is not a replacement for commercial-grade solutions like Microsoft Defender or Proofpoint.*

**Current Limitations:**
*   **Synthetic Anomaly Baselines**: Due to a lack of public enterprise telemetry, the anomaly engine relies on synthetic behavioral profiles.
*   **Static Ensemble Calibration**: Engine weights are manually tuned rather than dynamically learned.
*   **Third-Party Threat Feeds**: Relying on external APIs introduces uptime dependencies.
*   **Heuristic Document Scanning**: Identifies threat signatures but does not replace deep sandbox execution or traditional AV.

**Future Work:**
*   Dynamic weight calibration via Isotonic Regression.
*   SIEM integration for real-world telemetry ingestion.
*   Redis-backed session memory for prompt injection persistence.
*   Computer Vision (CV) based visual phishing detection.

---

## 🚀 Quick Start & Setup Guide

### 1. Prerequisites
- **Python 3.11** (Required for the AI backend ecosystem)
- **Node.js 18+** (Required for the frontend dashboard and extension builds)
- **Git**

### 2. Backend Setup (Run Once)

Initialize the virtual environment and install the required machine learning and server dependencies:

```bash
cd sentineliq/backend
python -m venv venv

# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

**Obtain a Free Gemini API Key (Highly Recommended)**
1. Visit [Google AI Studio](https://aistudio.google.com/)
2. Click **Get API Key** and copy it.
3. Paste it into your `backend/.env` file: `GEMINI_API_KEY=your_key_here`

*(Note: The system gracefully degrades to heuristics and templates if the Gemini key is omitted.)*

### 3. Running the Ecosystem

You will need two separate terminal windows for the backend and frontend.

**Terminal 1: Start the Backend (FastAPI)**
```bash
cd sentineliq/backend
venv\Scripts\activate      # Windows
# source venv/bin/activate # Mac/Linux
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
*API Documentation available at: [http://localhost:8000/docs](http://localhost:8000/docs)*

**Terminal 2: Start the Frontend (Vite/React)**
```bash
cd sentineliq/frontend
npm install
npm run dev
```
*Dashboard available at: [http://localhost:5173](http://localhost:5173)*

---

## ⚙️ Environment Variables Reference

| Variable | Required | Description |
|---|:---:|---|
| `GEMINI_API_KEY` | ❌ | Enables AI narration and advanced heuristic validation. |
| `FIREBASE_SERVICE_ACCOUNT` | ❌ | Path to Firebase JSON for remote logging (app works 100% locally without it). |
| `MODEL_CACHE_DIR` | ❌ | Directory for HuggingFace model downloads. Default: `./model_cache` |
| `ENVIRONMENT` | ❌ | `development` or `production` |

---

## 🔌 API Reference Highlights

The FastAPI backend exposes a robust suite of REST endpoints, built for low-latency integrations.

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | `GET` | System health check and model status verification. |
| `/api/v1/analyze` | `POST` | Primary analysis endpoint. Evaluates content against the 4-Engine Ensemble. |
| `/api/v1/incidents` | `GET` | Fetch historical security incidents. |
| `/docs` | `GET` | Explore the interactive OpenAPI (Swagger) interface. |

### `/api/v1/analyze` Request Schema (Form Data)

| Field | Type | Required | Description |
|---|---|:---:|---|
| `threat_type` | string | ✅ | Target engine: `phishing`, `url`, `prompt_injection`, or `anomaly`. |
| `content` | string | ✅* | The text, URL, or raw content to analyze. *(Optional if `file` is provided)* |
| `file` | file | ❌ | Direct file upload (PDF, TXT, EML, JSON, CSV). |

---

## 🔍 Chrome Web Store Reviewers Note

**Regarding `host_permissions` for localhost/127.0.0.1:**
SentinelIQ allows privacy-conscious enterprise users to self-host the FastAPI threat detection backend locally. The `http://127.0.0.1:8000/*` and `http://localhost:8000/*` permissions are explicitly requested to allow the extension to communicate with this user-hosted backend without triggering cross-origin network errors. The default configuration points to our secure production endpoint, and localhost is only accessed if the user manually configures it in the extension's Settings panel.

### Testing HTML Smuggling (Local Files)
If you are evaluating SentinelIQ against downloaded malicious `.html` files (HTML smuggling), **Chrome disables file access for extensions by default**. To enable this zero-day defense:
1. Navigate to `chrome://extensions/`
2. Click **Details** on the SentinelIQ extension.
3. Toggle **Allow access to file URLs** to **ON**.
Without this permission, Chrome physically blocks `content.js` from reading the DOM of local files, preventing SentinelIQ from scanning the payload.

---

<div align="center">
  <sub>Built with 🔒 by the SentinelIQ Security Team.</sub>
</div>
