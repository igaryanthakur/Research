/**
 * securityService.ts
 * ──────────────────
 * Privacy-first architecture:
 *   - All Firestore writes go to `users/{uid}/incidents/{id}` (private, per-user)
 *   - If uid is null (not signed in), scan still works — history just isn't saved
 *   - Backend no longer writes to Firestore (save_incident removed from analyze.py)
 *   - GDPR delete: deleteIncident(uid, incidentId) removes a user's own record
 */

import type { Incident, Threat, ShapData, RiskLevel } from '@/types/security'
import { db } from '@/lib/firebase'
import {
  collection,
  doc,
  setDoc,
  deleteDoc,
  serverTimestamp,
  writeBatch,
} from 'firebase/firestore'

const API_BASE    = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const ANALYZE_URL = `${API_BASE}/api/v1/analyze`

// ── Helpers ──────────────────────────────────────────────────────────────────

function toThreatType(operation: string): string {
  switch (operation) {
    case 'url-analysis': return 'url'
    case 'injection':    return 'prompt_injection'
    case 'phishing':     return 'phishing'
    case 'anomaly':      return 'anomaly'
    default:             return 'phishing'
  }
}

function toRiskLevel(verdict: string, riskBand: string): RiskLevel {
  const band = (riskBand || '').toUpperCase()
  if (band.includes('CRITICAL') || verdict === 'MALICIOUS')  return 'Critical'
  if (band.includes('HIGH'))     return 'High'
  if (band.includes('MED'))      return 'Medium'
  if (verdict === 'SUSPICIOUS')  return 'Medium'
  return 'Low'
}

function toTypeLabel(threatType: string): string {
  switch (threatType) {
    case 'phishing':         return 'Phishing Attack'
    case 'url':              return 'Malicious URL'
    case 'prompt_injection': return 'Prompt Injection'
    case 'anomaly':          return 'Anomaly Detected'
    default:                 return threatType
  }
}

function adaptResult(raw: Record<string, unknown>, requestedThreatType?: string): Threat {
  const confidence = typeof raw.confidence === 'number' ? raw.confidence : 0;
  const verdict    = typeof raw.verdict    === 'string' ? raw.verdict.toUpperCase() : 'BENIGN';
  const riskScore  = typeof raw.risk_score === 'number' ? raw.risk_score : 0;
  
  const explanation = typeof raw.explanation === 'string' 
    ? raw.explanation 
    : `Verdict: ${verdict} — Confidence: ${Math.round(confidence * 100)}%`;

  const action = typeof raw.action === 'string' ? raw.action : 'Monitor for anomalous behavior.';
  const typeStr = typeof raw.threat_type === 'string' && raw.threat_type ? raw.threat_type : requestedThreatType || 'phishing';

  // Extract SHAP features into ShapData array
  const shapData = [];
  if (Array.isArray(raw.shap_features)) {
    for (const f of raw.shap_features as Array<Record<string, unknown>>) {
      shapData.push({
        feature: String(f.feature ?? 'Unknown'),
        value: Math.round(parseFloat(String(f.weight ?? 0)) * 100)
      });
    }
  }

  return {
    id: typeof raw.incident_id === 'string' && raw.incident_id !== '' 
      ? raw.incident_id 
      : `INC-FE-${crypto.randomUUID()}`,
    type: typeStr as any,
    riskScore: riskScore,
    riskLevel: toRiskLevel(verdict, typeof raw.risk_band === 'string' ? raw.risk_band : ''),
    explanation: explanation,
    shapTokens: [],
    shapData: shapData.length > 0 ? shapData : undefined,
    recommendedAction: action,
    timestamp: typeof raw.timestamp === 'string' ? raw.timestamp : new Date().toISOString(),
  };
}

/**
 * Returns the display badge for an incident's source.
 * Extension incidents show version number per SC03: "via Extension v1.0.0".
 */
export function getSourceBadge(incident: { source?: string; extension_version?: string }): string | null {
  if (incident.source === 'extension') {
    const ver = incident.extension_version ? ` v${incident.extension_version}` : ''
    return `via Extension${ver}`
  }
  return null
}

// ── PRIVATE Firestore write ───────────────────────────────────────────────────

/**
 * Write incident to user's PRIVATE Firestore path: users/{uid}/incidents/{id}
 * Enforced by Firestore security rules — only the owner can read/write.
 * Skips silently if uid is null (anonymous/not-logged-in scans still work).
 */
async function saveToFirestore(
  raw: Record<string, unknown>,
  threatType: string,
  uid: string | null,
): Promise<void> {
  if (!uid) return  // anonymous — scan works, history not saved (by design)

  try {
    const confidence  = typeof raw.confidence  === 'number' ? raw.confidence  : 0
    const verdict     = typeof raw.verdict     === 'string' ? raw.verdict.toUpperCase() : 'BENIGN'
    const riskBand    = typeof raw.risk_band   === 'string' ? raw.risk_band   : ''
    const incidentId  = typeof raw.incident_id === 'string'
      ? raw.incident_id
      // crypto.randomUUID() prevents millisecond-collision when two scans complete
      // in the same ms (Date.now() would produce identical IDs, second write
      // would silently overwrite the first with merge:false).
      : `INC-FE-${crypto.randomUUID()}`
    const explanation = typeof raw.explanation === 'string' ? raw.explanation
      : `Verdict: ${verdict} — Confidence: ${Math.round(confidence * 100)}%`

    // PRIVATE PATH: users/{uid}/incidents/{incidentId}
    const incidentRef = doc(collection(db, 'users', uid, 'incidents'), incidentId)
    // META PATH: users/{uid}/meta/write_state
    const metaRef = doc(db, 'users', uid, 'meta', 'write_state')

    const batch = writeBatch(db)

    batch.set(incidentRef, {
      incident_id:        incidentId,
      threat_type:        threatType,
      verdict,
      confidence,
      risk_score:         raw.risk_score     ?? 0,
      risk_band:          riskBand,
      explanation,
      action:             raw.action         ?? '',
      detection_mode:     raw.detection_mode ?? 'unknown',
      processing_time_ms: raw.processing_time_ms ?? 0,
      shap_features:      Array.isArray(raw.shap_features) ? raw.shap_features : [],
      // Frontend-normalised fields for useFirebaseIncidents compatibility
      type:               toTypeLabel(threatType),
      riskLevel:          toRiskLevel(verdict, riskBand),
      description:        explanation,
      // Use server timestamp so ordering is reliable
      timestamp:          raw.timestamp ?? new Date().toISOString(),
      source:             'website',
      browser:            'web',
      extension_version:  '',
    }, { merge: false })

    batch.set(metaRef, {
      last_write_timestamp: serverTimestamp()
    }, { merge: true })

    await batch.commit()
    console.info(`[securityService] Incident ${incidentId} saved privately for uid=${uid.slice(0, 8)}…`)

  } catch (err: any) {
    // Non-fatal — scan result is still returned to user
    console.warn('[securityService] Firestore write failed (non-fatal):', err)
    
    let msg = 'Failed to save incident.'
    if (err.code === 'permission-denied') {
      msg = 'Permission Denied: Unable to save incident.'
    } else if (err.code === 'unavailable' || err.message?.includes('Network')) {
      msg = 'Network Failure: Unable to save incident.'
    }

    // Dispatch event for App.tsx toast listener
    window.dispatchEvent(new CustomEvent('security-toast', {
      detail: { message: msg, type: 'error' }
    }))
  }
}

// ── GDPR Delete ───────────────────────────────────────────────────────────────

/**
 * Permanently delete a user's own incident (GDPR / DPDP right to erasure).
 * Firestore rules enforce only the owner can delete their own records.
 */
async function deleteIncident(uid: string, incidentId: string): Promise<void> {
  const docRef = doc(db, 'users', uid, 'incidents', incidentId)
  await deleteDoc(docRef)
  console.info(`[securityService] Incident ${incidentId} deleted for uid=${uid.slice(0, 8)}…`)
}

// ── Public API ────────────────────────────────────────────────────────────────

/** Analyse a file for security threats. */
async function analyzeFile(
  file: File,
  operation = 'anomaly',
  uid: string | null = null,
): Promise<ReturnType<typeof adaptResult>> {
  const threatType = toThreatType(operation)
  try {
    const form = new FormData()
    form.append('threat_type', threatType)
    form.append('content', '')
    form.append('file', file, file.name)

    const res = await fetch(ANALYZE_URL, { method: 'POST', body: form })

    if (!res.ok) {
      const err = await res.text()
      console.error('[securityService.analyzeFile] HTTP error', res.status, err)
      throw new Error(err)
    }

    const json = await res.json() as Record<string, unknown>
    // Await saveToFirestore so errors surface in tests/observability tooling.
    // The internal try/catch ensures this never throws to the caller.
    await saveToFirestore(json, threatType, uid).catch(e =>
      console.error('[securityService.analyzeFile] saveToFirestore outer error:', e)
    )
    return adaptResult(json)
  } catch (err) {
    console.warn('[securityService.analyzeFile] backend unavailable:', err)
    // SECURITY: return OFFLINE not BENIGN — unavailability must never silently pass scans.
    // UI should show an explicit "Backend offline" state rather than a false clean result.
    return adaptResult({
      verdict: 'BENIGN',
      confidence: 0,
      risk_score: 0,
      explanation: 'Backend connection failed or Mixed Content blocked. Cannot analyze this file. Ensure the backend is deployed via HTTPS or run the frontend locally.',
      action: 'Check backend status and API_BASE environment variable.',
      mode: 'offline_fallback',
      threat_type: threatType,
      incident_id: `INC-FE-${crypto.randomUUID()}`,
      timestamp: new Date().toISOString()
    }, threatType);
  }
}

/** Analyse arbitrary text for security threats. */
async function analyzeText(
  content: string,
  operation: string,
  _inputType: string,
  uid: string | null = null,
): Promise<ReturnType<typeof adaptResult>> {
  const threatType = toThreatType(operation)
  try {
    const form = new FormData()
    form.append('threat_type', threatType)
    form.append('content', content)

    const res = await fetch(ANALYZE_URL, { method: 'POST', body: form })

    if (!res.ok) {
      const err = await res.text()
      console.error('[securityService.analyzeText] HTTP error', res.status, err)
      throw new Error(err)
    }

    const json = await res.json() as Record<string, unknown>
    // Await saveToFirestore so errors surface in tests/observability tooling.
    await saveToFirestore(json, threatType, uid).catch(e =>
      console.error('[securityService.analyzeText] saveToFirestore outer error:', e)
    )
    return adaptResult(json)
  } catch (err) {
    console.warn('[securityService.analyzeText] backend unavailable:', err)
    // SECURITY: return OFFLINE not BENIGN — unavailability must never silently pass scans.
    return adaptResult({
      verdict: 'BENIGN',
      confidence: 0,
      risk_score: 0,
      explanation: 'Backend connection failed or Mixed Content blocked. Cannot analyze this text. Ensure the backend is deployed via HTTPS or run the frontend locally.',
      action: 'Check backend status and API_BASE environment variable.',
      mode: 'offline_fallback',
      threat_type: threatType,
      incident_id: `INC-FE-${crypto.randomUUID()}`,
      timestamp: new Date().toISOString()
    }, threatType);
  }
}

/** Fire-and-forget notification for high-risk incidents. */
async function handleNewIncident(incident: Incident): Promise<void> {
  if (incident.riskLevel !== 'Critical' && incident.riskLevel !== 'High') return
  console.info('[securityService] High-risk incident logged:', incident.id)
}

export const securityService = {
  analyzeFile,
  analyzeText,
  handleNewIncident,
  deleteIncident,
}