// Firebase configuration and initialization for SentinelIQ
import { initializeApp, FirebaseApp } from 'firebase/app'
import { getFirestore, Firestore } from 'firebase/firestore'
import { getAnalytics, Analytics } from 'firebase/analytics'
import { getAuth, Auth, signInAnonymously, GoogleAuthProvider } from 'firebase/auth'

const firebaseConfig = {
  apiKey: 'AIzaSyABYnQ3LzEJ5awl7iVq4KusHpEUqFcK-c4',
  authDomain: 'cybershield-e57d9.firebaseapp.com',
  projectId: 'cybershield-e57d9',
  storageBucket: 'cybershield-e57d9.firebasestorage.app',
  messagingSenderId: '824054747297',
  appId: '1:824054747297:web:e69285e7126d59e616a0e0',
  measurementId: 'G-4LGHK5H280',
}

const firebaseApp: FirebaseApp = initializeApp(firebaseConfig)

export const db: Firestore = getFirestore(firebaseApp)
export const auth: Auth = getAuth(firebaseApp)
export const googleProvider = new GoogleAuthProvider()

// Analytics only available in browser context (not SSR)
let analyticsInstance: Analytics | null = null
if (typeof window !== 'undefined') {
  analyticsInstance = getAnalytics(firebaseApp)
}
export const analytics = analyticsInstance

/** Sign in anonymously so Firestore rules can scope reads/writes. */
export async function initFirebaseAuth(): Promise<void> {
  try {
    await signInAnonymously(auth)
  } catch (e) {
    console.warn('Firebase anonymous auth failed (offline?):', e)
  }
}

export default firebaseApp
