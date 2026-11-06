export type RiskLevel = 'Critical' | 'High' | 'Medium' | 'Low';

export interface Threat {
  id: string;
  type: 'phishing' | 'url' | 'injection' | 'anomaly';
  riskScore: number;
  riskLevel: RiskLevel;
  explanation: string;
  shapTokens: { token: string; importance: number }[];
  shapData?: ShapData[];
  recommendedAction: string;
  timestamp: string;
}

export interface Incident {
  id: string;
  timestamp: string;
  type: string;
  riskLevel: RiskLevel;
  description: string;
}

export interface ShapData {
  feature: string;
  value: number;
}
