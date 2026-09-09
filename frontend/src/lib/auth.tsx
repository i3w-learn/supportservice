import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import { GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signOut } from "firebase/auth"

import { auth, isFirebaseConfigured } from "@/firebase"

export interface AdminUser {
  uid: string
  email: string
  displayName: string
}

interface AuthContextValue {
  user: AdminUser | null
  loading: boolean
  error: string | null
  /** True when Firebase is not configured and we are running on mock data. */
  demo: boolean
  /**
   * Set when Firestore refuses our reads. Signing in proves identity; the
   * rules decide access by checking `admins/{uid}` (§9). Call `denyAccess`
   * from a listener's error handler on `permission-denied`.
   */
  accessDenied: boolean
  denyAccess: () => void
  signIn: () => Promise<void>
  signOutNow: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const DEMO_KEY = "support-desk.demo-user"

const DEMO_USER: AdminUser = {
  uid: "demo-admin",
  email: "partnerships@i3w.ai",
  displayName: "Manas Singh",
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const demo = !isFirebaseConfigured
  const [user, setUser] = useState<AdminUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [accessDenied, setAccessDenied] = useState(false)

  useEffect(() => {
    if (demo) {
      try {
        setUser(sessionStorage.getItem(DEMO_KEY) ? DEMO_USER : null)
      } catch {
        setUser(null)
      }
      setLoading(false)
      return
    }

    return onAuthStateChanged(auth!, (firebaseUser) => {
      setAccessDenied(false)
      setUser(
        firebaseUser
          ? {
              uid: firebaseUser.uid,
              email: firebaseUser.email ?? "",
              displayName: firebaseUser.displayName ?? firebaseUser.email ?? "Admin",
            }
          : null,
      )
      setLoading(false)
    })
  }, [demo])

  const denyAccess = useCallback(() => setAccessDenied(true), [])

  const signIn = useCallback(async () => {
    setError(null)
    setAccessDenied(false)

    if (demo) {
      try {
        sessionStorage.setItem(DEMO_KEY, "1")
      } catch {
        // session just will not survive a reload
      }
      setUser(DEMO_USER)
      return
    }

    try {
      await signInWithPopup(auth!, new GoogleAuthProvider())
    } catch (caught) {
      const code = (caught as { code?: string }).code ?? ""
      // Closing the popup yourself is not an error worth showing.
      if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") return
      setError("Sign-in failed. Check that Google sign-in is enabled for this project.")
    }
  }, [demo])

  const signOutNow = useCallback(async () => {
    if (demo) {
      try {
        sessionStorage.removeItem(DEMO_KEY)
      } catch {
        // nothing to clear
      }
      setUser(null)
      setAccessDenied(false)
      return
    }
    await signOut(auth!)
  }, [demo])

  const value = useMemo(
    () => ({ user, loading, error, demo, accessDenied, denyAccess, signIn, signOutNow }),
    [user, loading, error, demo, accessDenied, denyAccess, signIn, signOutNow],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used inside AuthProvider")
  return context
}
