import { useEffect, useState } from "react"
import { AlertTriangle, CheckCheck, Clock3, ImageIcon, Loader2, ShieldCheck } from "lucide-react"

import { FailedLozenge, ServiceTag, SlaLozenge, StatusLozenge } from "@/components/lozenge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { LANGUAGES, SERVICES, TEMPLATES } from "@/lib/types"
import type { Message, Ticket, TicketEvent } from "@/lib/types"
import { clockTime, dayLabel, formatCountdown, relativeTime, replyWindow } from "@/lib/window"

interface Props {
  ticket: Ticket | null
  onTake: (id: string) => void
  onNote: (id: string, text: string) => void
  onResolve: (id: string, text: string) => void
  onResend: (id: string) => void
  /** Set when a drag onto "Awaiting delivery" needs a resolution written. */
  startComposing?: boolean
}

export function TicketDetail({
  ticket,
  onTake,
  onNote,
  onResolve,
  onResend,
  startComposing = false,
}: Props) {
  const [draft, setDraft] = useState("")
  const [composing, setComposing] = useState(startComposing)
  const [noteDraft, setNoteDraft] = useState("")
  const [notingComposing, setNotingComposing] = useState(false)
  const [, tick] = useState(0)

  // The countdown is live because it changes what we are allowed to send.
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    setComposing(startComposing)
    setDraft("")
    setNotingComposing(false)
    setNoteDraft("")
  }, [ticket?.ticketId, startComposing])

  if (!ticket) {
    return (
      <div className="grid flex-1 place-items-center text-sm text-muted-foreground">
        Select a ticket.
      </div>
    )
  }

  const failed = ticket.resolution?.deliveryState === "failed"
  const canTake = ticket.status === "open"
  const canResolve = ticket.status === "open" || ticket.status === "in_progress"
  // messages/events live in subcollections and are optional on the base type.
  const messages = ticket.messages ?? []
  const events = ticket.events ?? []

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex flex-col gap-2.5 border-b px-5 py-3.5 pr-12">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">{ticket.ticketId}</span>
          <StatusLozenge status={ticket.status} />
          <SlaLozenge sla={ticket.slaState} />
          {failed && <FailedLozenge />}
        </div>
        <h1 className="text-lg font-semibold tracking-tight text-balance">
          {ticket.categoryLabel}
        </h1>
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
          <ServiceTag name={ticket.serviceName} color={SERVICES[ticket.serviceId].color} />
          <span aria-hidden>·</span>
          <span className="font-medium text-foreground">{ticket.contactName}</span>
          <span aria-hidden>·</span>
          <span>{ticket.centreName}</span>
          <span aria-hidden>·</span>
          <span className="font-mono">+{ticket.waNumber}</span>
          <span aria-hidden>·</span>
          <span>{LANGUAGES[ticket.language]}</span>
        </div>
      </header>

      <ReplyWindowBar ticket={ticket} />

      <Tabs defaultValue="conversation" className="flex min-h-0 flex-1 flex-col gap-0">
        <TabsList className="mx-5 mt-3 self-start">
          <TabsTrigger value="conversation">Conversation</TabsTrigger>
          <TabsTrigger value="activity">Activity · {events.length}</TabsTrigger>
        </TabsList>

        <TabsContent value="conversation" className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <Thread messages={messages} />
        </TabsContent>

        <TabsContent value="activity" className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <ActivityLog events={events} />
        </TabsContent>
      </Tabs>

      <footer className="flex flex-col gap-3 border-t bg-card px-5 py-3">
        {ticket.status === "closed" ? (
          <p className="text-xs text-muted-foreground">
            Closed means it reached their phone — a delivery receipt came back, not just that we
            pressed send.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {canTake && (
                <Button variant="outline" size="sm" onClick={() => onTake(ticket.ticketId)}>
                  Take this ticket
                </Button>
              )}
              {canResolve && (
                <Button size="sm" onClick={() => setComposing((v) => !v)}>
                  {composing ? "Cancel" : "Resolve…"}
                </Button>
              )}
              {failed && (
                <Button size="sm" onClick={() => onResend(ticket.ticketId)}>
                  Retry send
                </Button>
              )}
              {!notingComposing && (
                <Button variant="ghost" size="sm" onClick={() => setNotingComposing(true)}>
                  Add note
                </Button>
              )}
              <span className="ml-auto text-xs text-muted-foreground">{hintFor(ticket)}</span>
            </div>

            {notingComposing && (
              <div className="flex items-center gap-2">
                <Input
                  autoFocus
                  value={noteDraft}
                  onChange={(e) => setNoteDraft(e.target.value)}
                  placeholder="Internal note — never sent to the user"
                  className="h-8 flex-1 text-sm"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && noteDraft.trim()) {
                      onNote(ticket.ticketId, noteDraft.trim())
                      setNotingComposing(false)
                      setNoteDraft("")
                    }
                  }}
                />
                <Button
                  size="sm"
                  disabled={!noteDraft.trim()}
                  onClick={() => {
                    onNote(ticket.ticketId, noteDraft.trim())
                    setNotingComposing(false)
                    setNoteDraft("")
                  }}
                >
                  Save
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setNotingComposing(false)
                    setNoteDraft("")
                  }}
                >
                  Cancel
                </Button>
              </div>
            )}

            {composing && (
              <div className="flex flex-col gap-2.5">
                <SendModeNotice ticket={ticket} />
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={`What did you do to fix it? This goes to ${ticket.contactName} on WhatsApp.`}
                  className="min-h-20"
                />
                <div>
                  <Button
                    size="sm"
                    disabled={!draft.trim()}
                    onClick={() => {
                      onResolve(ticket.ticketId, draft.trim())
                      setComposing(false)
                      setDraft("")
                    }}
                  >
                    Send resolution
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </footer>
    </div>
  )
}

function ReplyWindowBar({ ticket }: { ticket: Ticket }) {
  const win = replyWindow(ticket.lastInboundAt)
  const tone =
    win.mode === "closed"
      ? "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300"
      : win.mode === "closing"
        ? "bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300"
        : "bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300"

  return (
    <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 border-b px-5 py-2 text-xs", tone)}>
      {win.mode === "closed" ? (
        <AlertTriangle className="size-3.5 shrink-0" />
      ) : (
        <ShieldCheck className="size-3.5 shrink-0" />
      )}
      {win.mode === "closed" ? (
        <span>24-hour window closed — replies must use an approved template</span>
      ) : (
        <>
          <span>Free text allowed — 24-hour window closes in</span>
          <span className="whitespace-nowrap rounded bg-black/5 px-1.5 py-0.5 font-mono tabular-nums dark:bg-white/10">
            {formatCountdown(win.msLeft)}
          </span>
        </>
      )}
    </div>
  )
}

function SendModeNotice({ ticket }: { ticket: Ticket }) {
  const win = replyWindow(ticket.lastInboundAt)

  if (win.sendsAs === "template") {
    return (
      <div className="flex gap-2 rounded-md bg-amber-50 p-2.5 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
        <div className="min-w-0">
          <p>
            <b className="font-semibold">The 24-hour window has closed.</b> This goes out as the
            approved {LANGUAGES[ticket.language]} template, not free text.
          </p>
          <pre className="mt-1.5 overflow-x-auto rounded border bg-background p-2 font-mono text-[11px] leading-relaxed text-foreground">
            {TEMPLATES[ticket.language]}
          </pre>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-2 rounded-md bg-emerald-50 p-2.5 text-xs text-emerald-900 dark:bg-emerald-500/10 dark:text-emerald-200">
      <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
      <p>
        <b className="font-semibold">Sends as free text.</b> {ticket.contactName} wrote{" "}
        {relativeTime(ticket.lastInboundAt)}, so the window is still open.
      </p>
    </div>
  )
}

function Thread({ messages }: { messages: Message[] }) {
  let lastDay: string | null = null

  return (
    <div className="flex flex-col gap-3">
      {messages.map((m) => {
        const day = dayLabel(m.createdAt)
        const showDay = day !== lastDay
        lastDay = day
        const out = m.direction === "out"

        return (
          <div key={m.messageId} className="flex flex-col gap-3">
            {showDay && (
              <div className="flex items-center gap-2.5">
                <Separator className="flex-1" />
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  {day}
                </span>
                <Separator className="flex-1" />
              </div>
            )}
            <div className={cn("flex max-w-[34rem] flex-col gap-1", out && "self-end items-end")}>
              {m.attachment ? (
                <AttachmentCard message={m} />
              ) : (
                <div
                  className={cn(
                    "rounded-lg px-3 py-2 text-sm leading-relaxed",
                    out
                      ? "bg-primary/10 text-foreground"
                      : "border bg-card text-card-foreground",
                  )}
                >
                  {m.text}
                </div>
              )}
              <div className="flex items-center gap-1.5 px-0.5 font-mono text-[10px] text-muted-foreground">
                <span>{clockTime(m.createdAt)}</span>
                {out && m.sentVia && (
                  <span
                    className={cn(
                      "rounded px-1 uppercase tracking-wide",
                      m.sentVia === "template"
                        ? "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300"
                        : "bg-muted",
                    )}
                  >
                    {m.sentVia}
                  </span>
                )}
                {out && m.providerStatus && <DeliveryMark status={m.providerStatus} />}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DeliveryMark({ status }: { status: NonNullable<Message["providerStatus"]> }) {
  if (status === "queued" || status === "sent") {
    return (
      <span className="flex items-center gap-0.5">
        <Loader2 className="size-2.5 animate-spin" />
        {status}
      </span>
    )
  }
  if (status === "failed") return <span className="text-red-500">failed ✗</span>
  return (
    <span className="flex items-center gap-0.5 text-sky-600 dark:text-sky-400">
      <CheckCheck className="size-3" />
      {status}
    </span>
  )
}

function AttachmentCard({ message }: { message: Message }) {
  const att = message.attachment!
  const pending = att.state === "pending"

  return (
    <div className="flex max-w-80 items-center gap-2.5 rounded-lg border bg-card p-2">
      <div
        className={cn(
          "grid size-13 shrink-0 place-items-center rounded-md border",
          pending
            ? "animate-pulse bg-muted text-muted-foreground"
            : "border-transparent bg-gradient-to-br from-slate-500 via-emerald-700 to-amber-700 text-white/90",
        )}
      >
        {pending ? <Clock3 className="size-5" /> : <ImageIcon className="size-5" />}
      </div>
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-medium">Photo</span>
        <span
          className={cn(
            "font-mono text-[10px]",
            pending ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground",
          )}
        >
          {pending
            ? "still arriving…"
            : `${Math.round((att.sizeBytes ?? 0) / 1024)} KB · signed URL, 15 min`}
        </span>
      </div>
    </div>
  )
}

function ActivityLog({ events }: { events: TicketEvent[] }) {
  return (
    <ol className="flex flex-col">
      {[...events].reverse().map((e, i, all) => (
        <li key={e.eventId} className="grid grid-cols-[14px_1fr_auto] gap-2.5 py-1.5 text-sm">
          <span className="relative grid place-items-center">
            <span
              className={cn(
                "z-10 size-1.5 rounded-full",
                e.actor === "admin"
                  ? "bg-primary"
                  : e.actor === "system"
                    ? "bg-amber-500"
                    : "bg-muted-foreground/50",
              )}
            />
            {i < all.length - 1 && (
              <span className="absolute inset-y-0 -bottom-3 w-px bg-border" aria-hidden />
            )}
          </span>
          <span className="text-muted-foreground">
            <b className="font-medium text-foreground">{describe(e)}</b> · {e.actor}
          </span>
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
            {relativeTime(e.at)}
          </span>
        </li>
      ))}
    </ol>
  )
}

function describe(e: TicketEvent): string {
  switch (e.type) {
    case "created":
      return "Ticket created"
    case "status_changed":
      return `Status changed: ${e.from} → ${e.to}`
    case "note":
      return `Note: ${e.note}`
    case "resolution_sent":
      return "Resolution sent"
    case "delivered":
      return "Delivered to phone — ticket closed"
    case "sla_flagged":
      return `SLA flagged — ${e.note}`
    case "media_failed":
      return e.note ?? "Media failed"
    case "message_added":
      return "Message added to open ticket"
  }
}

function hintFor(t: Ticket): string {
  if (t.resolution?.deliveryState === "failed") return "Send failed once. The hourly sweep will retry."
  if (t.status === "resolved") return "Waiting for the delivery receipt to close it."
  if (t.slaState === "breached") return "48h with no first response."
  if (t.slaState === "reminder_due") return "24h with no first response."
  return ""
}
