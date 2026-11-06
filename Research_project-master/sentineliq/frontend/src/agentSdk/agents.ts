import { AgentConfig } from './types';
import { z } from 'zod';

export const AGENT_CONFIGS: AgentConfig[] = [
  {
    "id": "4fcf44b7-9a5c-473a-a933-916ffc9e6ccf",
    "name": "SentinelIQ Security Analyst",
    "description": "An advanced AI security agent designed to monitor, analyze, and mitigate cybersecurity threats in real-time. It processes security logs, identifies anomalies, and provides human-readable explanations using SHAP logic.",
    "triggerEvents": [
      {
        "name": "file_upload_analysis",
        "description": "Fires when a user uploads a file (.pdf, .eml, .json, .csv, .txt). The agent scans the content, identifies threats, and generates an AI threat result card.",
        "type": "sync",
        "outputSchema": z.any()
      },
      {
        "name": "high_risk_incident_detected",
        "description": "Fires when a new incident with a 'Critical' or 'High' risk level enters the live feed, prompting the agent to alert the user.",
        "type": "async"
      },
      {
        "name": "threat_explanation_request",
        "description": "Fires when a user clicks on an incident or asks for SHAP chart details, triggering a technical breakdown of feature importance.",
        "type": "sync",
        "outputSchema": z.any()
      }
    ],
    "config": {
      "appId": "bb578463-c24b-42aa-ba4c-929a72f54b35",
      "accountId": "bdd4f6a1-37cf-4180-af81-8379cdce7db5",
      "widgetKey": "SfcmHR25avFNZ2nMZt6nMm3EaJmbJzlEDryVwUQe"
    }
  }
];