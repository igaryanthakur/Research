/**
 * useFirebaseIncidents.ts
 * ───────────────────────
 * PRIVACY-FIRST: Reads ONLY from `users/{uid}/incidents` — isolated per user.
 * No admin, no backend, no other user can ever read this data.
 *
 * If uid is null (not signed in), returns empty list immediately.
 * Anonymous auth is intentionally NOT used — history requires a real account.
 */
import { useEffect, useState, useRef } from 'react'
import {
  collection,
  onSnapshot,
  query,
  orderBy,
  limit,
  Timestamp,
  QueryDocumentSnapshot,
  DocumentData,
} from 'firebase/firestore'
import { db } from '@/lib/firebase'
import type { Incident, RiskLevel } from '@/types/security'

const MAX_ITEMS = 50

// ── Normalisation helpers ──────────────────────────────────────────────────────

function toRiskLevel(raw: unknown): RiskLevel {
  const s = String(raw ?? '').toUpperCase()
  if (s.includes('CRITICAL')) return 'Critical'
  if (s.includes('HIGH'))     return 'High'
  if (s.includes('MED'))      return 'Medium'
  return 'Low'
}

function toTypeLabel(raw: unknown): string {
  const s = String(raw ?? '').toLowerCase()
  if (s.includes('phish'))  return 'Phishing Attack'
  if (s.includes('url'))    return 'Malicious URL'
  if (s.includes('inject')) return 'Prompt Injection'
  if (s.includes('anomaly'))return 'Anomaly Detected'
  if (s.length > 0)         return String(raw)
  return 'Unknown'
}

function docToIncident(doc: QueryDocumentSnapshot<DocumentData>): Incident {
  const d = doc.data()

  // Timestamp
  let timestamp: string
  if (d.timestamp instanceof Timestamp) {
    timestamp = d.timestamp.toDate().toISOString()
  } else if (typeof d.timestamp === 'string') {
    timestamp = d.timestamp
  } else {
    timestamp = new Date().toISOString()
  }

  // Risk level — accept both frontend (riskLevel) and backend (risk_band) fields
  const riskLevel: RiskLevel = d.riskLevel
    ? (['Critical', 'High', 'Medium', 'Low'].includes(d.riskLevel) ? d.riskLevel as RiskLevel : 'Low')
    : toRiskLevel(d.risk_band ?? d.risk_score ?? '')

  // Type
  const type = typeof d.type === 'string' && d.type
    ? d.type
    : toTypeLabel(d.threat_type)

  // Description
  const description = typeof d.description === 'string' && d.description
    ? d.description
    : typeof d.explanation === 'string' && d.explanation
      ? d.explanation
      : typeof d.verdict === 'string'
        ? `Verdict: ${d.verdict} — Confidence: ${Math.round((d.confidence ?? 0) * 100)}%`
        : 'Analysis completed.'

  return { id: doc.id, timestamp, type, riskLevel, description }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseFirebaseIncidentsReturn {
  incidents: Incident[]
  loading:   boolean
  error:     string | null
  isLive:    boolean
}

/**
 * Real-time Firestore incidents hook — PRIVATE per-user.
 *
 * @param uid  Firebase UID of the signed-in user. Pass null if not signed in.
 */
export function useFirebaseIncidents(uid: string | null): UseFirebaseIncidentsReturn {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading,   setLoading  ] = useState(true)
  const [error,     setError    ] = useState<string | null>(null)
  const [isLive,    setIsLive   ] = useState(false)
  const unsubRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    // No uid → not signed in — immediately clear and stop loading
    if (!uid) {
      setIncidents([])
      setLoading(false)
      setIsLive(false)
      setError(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)

    // PRIVATE PATH: users/{uid}/incidents — Firestore rules enforce isolation
    const q = query(
      collection(db, 'users', uid, 'incidents'),
      orderBy('timestamp', 'desc'),
      limit(MAX_ITEMS)
    )

    unsubRef.current = onSnapshot(
      q,
      snapshot => {
        if (cancelled) return
        setIncidents(snapshot.docs.map(docToIncident))
        setLoading(false)
        setIsLive(true)
        setError(null)
      },
      err => {
        if (cancelled) return
        console.error('[useFirebaseIncidents]', err)
        const msg = err.message ?? ''
        if (msg.includes('not found') || msg.includes('NOT_FOUND')) {
          setError('Firestore database not provisioned. Go to Firebase Console → Firestore Database → Create database.')
        } else if (msg.includes('Missing or insufficient permissions')) {
          setError('Firestore permission denied. Apply the security rules from the implementation plan.')
        } else {
          setError(msg || 'Failed to connect to Firebase')
        }
        setLoading(false)
        setIsLive(false)
      }
    )

    return () => {
      cancelled = true
      unsubRef.current?.()
    }
  }, [uid])

  return { incidents, loading, error, isLive }
}
