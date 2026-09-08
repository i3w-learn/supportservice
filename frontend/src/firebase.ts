// Reads only. Every write goes through the REST API (design §1).
// These values are public by design — the security rules are the wall (§9).
import { initializeApp } from "firebase/app"
import type { FirebaseApp } from "firebase/app"
import { connectAuthEmulator, getAuth } from "firebase/auth"
import type { Auth } from "firebase/auth"
import { connectFirestoreEmulator, getFirestore } from "firebase/firestore"
import type { Firestore } from "firebase/firestore"

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

/** False until .env.local is filled in. Until then the app runs on mock data. */
export const isFirebaseConfigured = Boolean(config.apiKey && config.projectId)

let app: FirebaseApp | null = null
let authInstance: Auth | null = null
let dbInstance: Firestore | null = null

if (isFirebaseConfigured) {
  app = initializeApp(config)
  authInstance = getAuth(app)
  dbInstance = getFirestore(app)

  if (import.meta.env.VITE_USE_EMULATORS === "true") {
    connectAuthEmulator(authInstance, "http://localhost:9099", { disableWarnings: true })
    connectFirestoreEmulator(dbInstance, "localhost", 8081)
  }
}

export const auth = authInstance
export const db = dbInstance
