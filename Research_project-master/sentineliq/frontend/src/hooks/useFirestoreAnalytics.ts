/**
 * useFirestoreAnalytics.ts
 * ────────────────────────
 * Aggregates real Firestore incident documents into chart-ready data for the
 * Threat Analysis dashboard. Uses the same real-time onSnapshot listener as
 * useFirebaseIncidents so charts update the moment a new scan completes.
 */
import { useEffect, useState } from 'react'
import { collection, onSnapshot, query, orderBy, limit } from 'firebase/firestore'
import { db } from '@/lib/firebase'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ThreatFreqPoint {
  name: string
  frequency: number
  severityScore: number
}

export interface HourPoint {
  hour: string
  threats: number
}

export interface SeverityPoint {
  name: string
  value: number
  color: string
}

export interface RecentIncident {
  id: string
  threat_type: string
  verdict: string
  confidence: number
  risk_band: string
  riskLevel: string
  explanation: string
  action: string
  detection_mode: string
  shap_features: { feature: string; weight: number; direction: string }[]
  timestamp: string
  processing_time_ms: number
}

export interface AnalyticsData {
  threatFreq:    ThreatFreqPoint[]
  peakHours:     HourPoint[]
  severityDist:  SeverityPoint[]
  totalScans:    number
  totalMalicious: number
  avgConfidence: number
  recentIncidents: RecentIncident[]
  loading: boolean
  error: string | null
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SEVERITY_COLORS: Record<string, string> = {
  Critical: '#ef4444',
  High:     '#f97316',
  Medium:   '#eab308',
  Low:      '#22c55e',
}

const THREAT_LABELS: Record<string, string> = {
  phishing:         'Phishing',
  url:              'URL Scan',
  prompt_injection: 'Injection',
  anomaly:          'Anomaly',
}

function toRiskLevel(band: string, verdict: string): string {
  const b = (band || '').toUpperCase()
  if (b.includes('CRITICAL') || verdict === 'MALICIOUS') return 'Critical'
  if (b.includes('HIGH'))     return 'High'
  if (b.includes('MED'))      return 'Medium'
  if (verdict === 'SUSPICIOUS') return 'Medium'
  return 'Low'
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFirestoreAnalytics(uid: string | null): AnalyticsData {
  const [data, setData] = useState<AnalyticsData>({
    threatFreq: [], peakHours: [], severityDist: [],
    totalScans: 0, totalMalicious: 0, avgConfidence: 0,
    recentIncidents: [], loading: true, error: null,
  })

  useEffect(() => {
    if (!uid) {
      setData({
        threatFreq: defaultThreatFreq(),
        peakHours: Array.from({ length: 24 }, (_, i) => ({ hour: `${String(i).padStart(2, '0')}:00`, threats: 0 })),
        severityDist: defaultSeverityDist(),
        totalScans: 0, totalMalicious: 0, avgConfidence: 0,
        recentIncidents: [], loading: false, error: null,
      })
      return
    }

    let cancelled = false

    const bootstrap = async () => {
      if (cancelled) return

      try {
        const q = query(
          collection(db, 'users', uid, 'incidents'),
          orderBy('timestamp', 'desc'),
          limit(5000),
        )

        const unsub = onSnapshot(q, snapshot => {
          if (cancelled) return
          const docs = snapshot.docs.map(d => d.data() as Record<string, any>)

          // ── Aggregate threat frequencies ──────────────────────────────────
          const freqMap: Record<string, { count: number; totalConf: number }> = {}
          const hourMap: Record<string, number> = {}
          const severityMap: Record<string, number> = { Critical: 0, High: 0, Medium: 0, Low: 0 }
          let totalMalicious = 0
          let totalConf = 0
          const recent: RecentIncident[] = []

          docs.forEach(d => {
            const tt = d.threat_type || 'unknown'
            const label = THREAT_LABELS[tt] || tt
            const conf = typeof d.confidence === 'number' ? d.confidence : 0
            const verdict = (d.verdict || '').toUpperCase()
            const band = d.risk_band || ''
            const riskLevel = toRiskLevel(band, verdict)

            if (!freqMap[label]) freqMap[label] = { count: 0, totalConf: 0 }
            freqMap[label].count++
            freqMap[label].totalConf += conf

            // Hour bucket
            const ts = d.timestamp ? new Date(d.timestamp) : new Date()
            const h = `${String(ts.getHours()).padStart(2, '0')}:00`
            hourMap[h] = (hourMap[h] || 0) + 1

            // Severity
            severityMap[riskLevel] = (severityMap[riskLevel] || 0) + 1

            if (verdict === 'MALICIOUS') totalMalicious++
            totalConf += conf

            // Build recent incidents (for modal)
            recent.push({
              id:               d.incident_id || d.id || String(Math.random()),
              threat_type:      tt,
              verdict,
              confidence:       conf,
              risk_band:        band,
              riskLevel,
              explanation:      d.explanation || d.description || '',
              action:           d.action || '',
              detection_mode:   d.detection_mode || d.narration_mode || 'heuristic',
              shap_features:    Array.isArray(d.shap_features) ? d.shap_features : [],
              timestamp:        d.timestamp || new Date().toISOString(),
              processing_time_ms: d.processing_time_ms || 0,
            })
          })

          const totalScans = docs.length

          // ── Chart arrays ──────────────────────────────────────────────────
          const threatFreq: ThreatFreqPoint[] = Object.entries(freqMap).map(([name, v]) => ({
            name,
            frequency: v.count,
            severityScore: Math.round((v.totalConf / v.count) * 100),
          }))

          // Fill hours 00-23
          const peakHours: HourPoint[] = Array.from({ length: 24 }, (_, i) => {
            const h = `${String(i).padStart(2, '0')}:00`
            return { hour: h, threats: hourMap[h] || 0 }
          })

          const total = totalScans || 1
          const severityDist: SeverityPoint[] = Object.entries(severityMap).map(([name, count]) => ({
            name,
            value: Math.round((count / total) * 100),
            color: SEVERITY_COLORS[name],
          }))

          setData({
            threatFreq: threatFreq.length ? threatFreq : defaultThreatFreq(),
            peakHours,
            severityDist: severityDist.length ? severityDist : defaultSeverityDist(),
            totalScans,
            totalMalicious,
            avgConfidence: totalScans > 0 ? Math.round((totalConf / totalScans) * 100) : 0,
            recentIncidents: recent,
            loading: false,
            error: null,
          })
        }, err => {
          if (cancelled) return
          setData(prev => ({ ...prev, loading: false, error: err.message }))
        })

        return unsub
      } catch (err: any) {
        if (!cancelled) setData(prev => ({ ...prev, loading: false, error: err.message }))
        return () => {}
      }
    }

    let unsub: (() => void) | undefined
    bootstrap().then(fn => { unsub = fn })
    return () => { cancelled = true; unsub?.() }
  }, [uid])

  return data
}

// ── Fallback data when no incidents exist yet ─────────────────────────────────
function defaultThreatFreq(): ThreatFreqPoint[] {
  return [
    { name: 'Phishing',  frequency: 0, severityScore: 0 },
    { name: 'URL Scan',  frequency: 0, severityScore: 0 },
    { name: 'Injection', frequency: 0, severityScore: 0 },
    { name: 'Anomaly',   frequency: 0, severityScore: 0 },
  ]
}

function defaultSeverityDist(): SeverityPoint[] {
  return [
    { name: 'Critical', value: 0, color: '#ef4444' },
    { name: 'High',     value: 0, color: '#f97316' },
    { name: 'Medium',   value: 0, color: '#eab308' },
    { name: 'Low',      value: 0, color: '#22c55e' },
  ]
}
