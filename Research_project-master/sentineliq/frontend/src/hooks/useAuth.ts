/**
 * useAuth.ts
 * ──────────
 * Lightweight Firebase Auth state hook.
 * Wraps onAuthStateChanged so every component gets live user/uid state
 * without extra boilerplate.
 *
 * Usage:
 *   const { user, uid, loading } = useAuth()
 *   if (!uid) { // not signed in }
 */
import { useEffect, useState } from 'react'
import { onAuthStateChanged, User } from 'firebase/auth'
import { auth } from '@/lib/firebase'

export interface UseAuthReturn {
  /** Full Firebase User object, or null if not signed in */
  user: User | null
  /** Shortcut: user.uid or null */
  uid:  string | null
  /** True during the initial auth state resolution — prevents flash of wrong UI */
  loading: boolean
  /** User's display name (Google / email prefix) */
  displayName: string | null
  /** User's email address */
  email: string | null
  /** User's photo URL (Google avatar) */
  photoURL: string | null
}

export function useAuth(): UseAuthReturn {
  const [user,    setUser   ] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser)
      setLoading(false)
    })
    return unsubscribe
  }, [])

  return {
    user,
    uid:         user?.uid         ?? null,
    loading,
    displayName: user?.displayName ?? null,
    email:       user?.email       ?? null,
    photoURL:    user?.photoURL    ?? null,
  }
}
