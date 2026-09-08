import { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronRight, Loader2, LogOut } from "lucide-react"

import { Board } from "@/components/board"
import { Login } from "@/components/login"
import { Sidebar, needsAttention } from "@/components/sidebar"
import type { ViewKey } from "@/components/sidebar"
import { ThemeToggle } from "@/components/theme-toggle"
import { TicketDetail } from "@/components/ticket-detail"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { TooltipProvider } from "@/components/ui/tooltip"
import { useAuth } from "@/lib/auth"
import { MOCK_TICKETS, nextId } from "@/lib/mock"
import { checkTransition } from "@/lib/transitions"
import type { ServiceId, Ticket, TicketStatus } from "@/lib/types"
import { replyWindow } from "@/lib/window"

export default function App() {
  const { user, loading, signOutNow } = useAuth()
  const [tickets, setTickets] = useState<Ticket[]>(MOCK_TICKETS)
  const [service, setService] = useState<ServiceId | "all">("all")
  const [view, setView] = useState<ViewKey>("all")
  const [query, setQuery] = useState("")
  const [openId, setOpenId] = useState<string | null>(null)
  const [composeOnOpen, setComposeOnOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const say = useCallback((message: string) => {
    setToast(message)
    setTimeout(() => setToast(null), 3000)
  }, [])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return tickets.filter((t) => {
      if (service !== "all" && t.serviceId !== service) return false
      if (view === "attention" && !needsAttention(t)) return false
      if (!needle) return true
      return `${t.ticketId} ${t.contactName} ${t.centreName} ${t.categoryLabel} ${t.description}`
        .toLowerCase()
        .includes(needle)
    })
  }, [tickets, service, view, query])

  const selected = tickets.find((t) => t.ticketId === openId) ?? null
  const alerts = tickets.filter(
    (t) => t.slaState !== "ok" || t.resolution?.deliveryState === "failed",
  ).length

  const patch = useCallback((id: string, fn: (t: Ticket) => Ticket) => {
    setTickets((all) => all.map((t) => (t.ticketId === id ? fn(t) : t)))
  }, [])

  const changeStatus = useCallback(
    (id: string, to: TicketStatus, from: TicketStatus) => {
      patch(id, (t) => ({
        ...t,
        status: to,
        firstResponseAt: t.firstResponseAt ?? (to === "in_progress" ? Date.now() : null),
        updatedAt: Date.now(),
        events: [
          ...t.events,
          {
            eventId: nextId("e"),
            type: "status_changed",
            from,
            to,
            actor: "admin",
            note: null,
            at: Date.now(),
          },
        ],
      }))
    },
    [patch],
  )

  // Dragging a card is a status transition, so it obeys the same table the API
  // enforces (§8). Illegal moves are refused rather than snapped back silently.
  const handleMove = useCallback(
    (id: string, to: TicketStatus) => {
      const ticket = tickets.find((t) => t.ticketId === id)
      if (!ticket) return

      const check = checkTransition(ticket.status, to)
      if (!check.ok) {
        say(check.reason)
        return
      }

      if (check.needsResolution) {
        setOpenId(id)
        setComposeOnOpen(true)
        say("Resolving sends a WhatsApp message — write it first.")
        return
      }

      changeStatus(id, to, ticket.status)
      say(`${id} → ${to.replace("_", " ")}`)
    },
    [tickets, changeStatus, say],
  )

  const handleTake = useCallback(
    (id: string) => {
      changeStatus(id, "in_progress", "open")
      say(`${id} is now in progress`)
    },
    [changeStatus, say],
  )

  const handleNote = useCallback(
    (id: string) => {
      patch(id, (t) => ({
        ...t,
        updatedAt: Date.now(),
        events: [
          ...t.events,
          {
            eventId: nextId("e"),
            type: "note",
            actor: "admin",
            note: "Checked with the field coordinator",
            at: Date.now(),
          },
        ],
      }))
      say("Note added — never sent to the user")
    },
    [patch, say],
  )

  // Resolve → send → delivery receipt → closed (§4.3). The admin never closes
  // a ticket; the receipt does.
  const dispatch = useCallback(
    (id: string, text: string | null) => {
      const ticket = tickets.find((t) => t.ticketId === id)
      if (!ticket) return
      const via = replyWindow(ticket.lastInboundAt).sendsAs
      const at = Date.now()

      patch(id, (t) => ({
        ...t,
        status: "resolved",
        resolvedAt: text ? at : t.resolvedAt,
        updatedAt: at,
        resolution: {
          text: text ?? t.resolution?.text ?? "",
          sentAt: at,
          deliveryState: "queued",
          attempts: (t.resolution?.attempts ?? 0) + 1,
        },
        messages: text
          ? [
              ...t.messages,
              {
                messageId: nextId("m"),
                direction: "out",
                ticketId: id,
                type: "text",
                text,
                sentVia: via,
                providerStatus: "queued",
                createdAt: at,
              },
            ]
          : t.messages.map((m, i) =>
              i === t.messages.length - 1 ? { ...m, providerStatus: "queued" as const } : m,
            ),
        events: [
          ...t.events,
          {
            eventId: nextId("e"),
            type: "resolution_sent",
            actor: "admin",
            note: text ? null : "Re-sent after failure",
            at,
          },
        ],
      }))

      setComposeOnOpen(false)
      say(text ? `Sent as ${via === "template" ? "approved template" : "free text"}` : "Retrying…")

      const mark = (status: "sent" | "delivered") =>
        patch(id, (t) => ({
          ...t,
          messages: t.messages.map((m, i) =>
            i === t.messages.length - 1 ? { ...m, providerStatus: status } : m,
          ),
          resolution: t.resolution ? { ...t.resolution, deliveryState: status } : null,
          ...(status === "delivered"
            ? {
                status: "closed" as const,
                closedAt: Date.now(),
                slaState: "ok" as const,
                updatedAt: Date.now(),
                events: [
                  ...t.events,
                  {
                    eventId: nextId("e"),
                    type: "delivered" as const,
                    actor: "system" as const,
                    note: "Delivery receipt received",
                    at: Date.now(),
                  },
                ],
              }
            : {}),
        }))

      setTimeout(() => mark("sent"), 900)
      setTimeout(() => {
        mark("delivered")
        say(`Delivery receipt received — ${id} closed`)
      }, 2600)
    },
    [tickets, patch, say],
  )

  // The 2-minute media cron landing a deferred attachment (§4.1 step 7).
  useEffect(() => {
    const timer = setTimeout(() => {
      patch("TKT-20260908-0041", (t) => ({
        ...t,
        messages: t.messages.map((m) =>
          m.attachment?.state === "pending"
            ? { ...m, attachment: { ...m.attachment, state: "stored", sizeBytes: 839_680 } }
            : m,
        ),
      }))
    }, 7000)
    return () => clearTimeout(timer)
  }, [patch])

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!user) return <Login />

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex h-screen flex-col bg-background text-foreground">
        <header className="shrink-0 border-b px-5 py-3">
          <nav className="flex items-center gap-1 text-xs text-muted-foreground">
            <span>i3w.ai</span>
            <ChevronRight className="size-3" />
            <span>Support</span>
          </nav>

          <div className="mt-1.5 flex items-center gap-3">
            <h1 className="text-xl font-semibold tracking-tight">Board</h1>

            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search"
              className="ml-4 h-8 w-56 text-sm"
            />

            <div className="flex-1" />

            {alerts > 0 && (
              <button
                type="button"
                onClick={() => setView("attention")}
                className="text-xs font-medium text-red-600 hover:underline dark:text-red-400"
              >
                {alerts} need attention
              </button>
            )}

            <ThemeToggle />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="size-8 rounded-full p-0" aria-label="Account">
                  <Avatar className="size-7">
                    <AvatarFallback className="text-[10px]">
                      {user.displayName
                        .split(" ")
                        .slice(0, 2)
                        .map((part) => part[0])
                        .join("")
                        .toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="font-normal">
                  <p className="text-sm font-medium">{user.displayName}</p>
                  <p className="text-xs text-muted-foreground">{user.email}</p>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => void signOutNow()} className="gap-2">
                  <LogOut className="size-4" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <Sidebar
            tickets={tickets}
            view={view}
            service={service}
            onView={setView}
            onService={setService}
          />

          <main className="min-h-0 flex-1 pt-4">
            <Board tickets={visible} onOpen={setOpenId} onMove={handleMove} />
          </main>
        </div>

        <Sheet
          open={openId !== null}
          onOpenChange={(next) => {
            if (!next) {
              setOpenId(null)
              setComposeOnOpen(false)
            }
          }}
        >
          <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-[34rem]">
            <SheetTitle className="sr-only">
              {selected ? selected.categoryLabel : "Ticket"}
            </SheetTitle>
            <TicketDetail
              ticket={selected}
              startComposing={composeOnOpen}
              onTake={handleTake}
              onNote={handleNote}
              onResolve={(id, text) => dispatch(id, text)}
              onResend={(id) => dispatch(id, null)}
            />
          </SheetContent>
        </Sheet>

        {toast && (
          <div
            role="status"
            aria-live="polite"
            className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-md bg-foreground px-3.5 py-2 text-sm text-background shadow-lg"
          >
            {toast}
          </div>
        )}
      </div>
    </TooltipProvider>
  )
}
