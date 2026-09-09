import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth"

/**
 * Signing in is not the same as having access. Firebase Auth lets anyone
 * create an account in the project; the rules then check membership in
 * `admins/` (§9). Without this screen a stranger — or a colleague who has
 * not been added yet — sees an empty board and reports it as broken.
 */
export function NotAuthorised() {
  const { user, signOutNow } = useAuth()

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <div className="flex justify-end p-4">
        <ThemeToggle />
      </div>

      <main className="flex flex-1 items-center justify-center px-6 pb-32">
        <div className="w-full max-w-72 text-center">
          <h1 className="text-lg font-semibold tracking-tight">No access</h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            <span className="font-medium text-foreground">{user?.email}</span> is signed in but
            is not on the admin list, so there is nothing to show.
          </p>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            Ask an existing admin to add you. It takes one document.
          </p>

          <Button variant="outline" onClick={() => void signOutNow()} className="mt-6 w-full">
            Sign out
          </Button>
        </div>
      </main>
    </div>
  )
}
