import { Loader2 } from "lucide-react"
import { useState } from "react"

import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth"

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="#4285F4"
        d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.3-2.1 3.5-5.2 3.5-8.8Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.2 0 5.9-1.1 7.9-2.9l-3.9-3c-1 .7-2.4 1.1-4 1.1-3 0-5.6-2-6.6-4.8H1.4v3.1A12 12 0 0 0 12 24Z"
      />
      <path fill="#FBBC05" d="M5.4 14.4a7.2 7.2 0 0 1 0-4.6V6.7H1.4a12 12 0 0 0 0 10.8l4-3.1Z" />
      <path
        fill="#EA4335"
        d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.4 6.7l4 3.1C6.4 6.9 9 4.8 12 4.8Z"
      />
    </svg>
  )
}

export function Login() {
  const { signIn, error, demo } = useAuth()
  const [busy, setBusy] = useState(false)

  const handle = async () => {
    setBusy(true)
    try {
      await signIn()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <div className="flex justify-end p-4">
        <ThemeToggle />
      </div>

      <main className="flex flex-1 items-center justify-center px-6 pb-32">
        <div className="w-full max-w-64 text-center">
          <h1 className="text-lg font-semibold tracking-tight">Support Desk</h1>
          <p className="mt-1 text-sm text-muted-foreground">Admin access only</p>

          <Button onClick={handle} disabled={busy} className="mt-7 w-full gap-2">
            {busy ? <Loader2 className="size-4 animate-spin" /> : <GoogleMark />}
            {busy ? "Signing in…" : "Continue with Google"}
          </Button>

          {error && (
            <p className="mt-3 text-sm text-red-600 dark:text-red-400" role="alert">
              {error}
            </p>
          )}

          {demo && (
            <p className="mt-4 text-xs text-muted-foreground">
              Demo mode — no Firebase config, running on mock data.
            </p>
          )}
        </div>
      </main>
    </div>
  )
}
