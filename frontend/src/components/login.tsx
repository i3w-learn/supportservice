import { Loader2, Lock } from "lucide-react"
import { useState } from "react"

import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useAuth } from "@/lib/auth"

export function Login() {
  const { signIn, error, demo } = useAuth()
  const [busy, setBusy] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")

  const handle = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) return
    setBusy(true)
    try {
      await signIn(email, password)
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
        <form onSubmit={handle} className="w-full max-w-72 text-center">
          <h1 className="text-lg font-semibold tracking-tight">Support Desk</h1>
          <p className="mt-1 text-sm text-muted-foreground">Admin access only</p>

          <div className="mt-6 space-y-3 text-left">
            <Input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          <Button type="submit" disabled={busy} className="mt-4 w-full gap-2">
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Lock className="size-4" />}
            {busy ? "Signing in…" : "Sign in"}
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
        </form>
      </main>
    </div>
  )
}
