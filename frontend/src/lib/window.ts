import { WHATSAPP_WINDOW_HOURS } from "./types"

const HOUR = 3_600_000

export type WindowMode = "open" | "closing" | "closed"

export interface ReplyWindow {
  mode: WindowMode
  msLeft: number
  /** What the channel module will actually do (§4.3). */
  sendsAs: "freeform" | "template"
}

/**
 * The 24-hour rule. WhatsApp only allows free text within 24 hours of the
 * contact's last inbound message; after that only an approved template goes
 * out. This is why `lastInboundAt` is load-bearing in the schema.
 */
export function replyWindow(lastInboundAt: number, now = Date.now()): ReplyWindow {
  const msLeft = lastInboundAt + WHATSAPP_WINDOW_HOURS * HOUR - now
  if (msLeft <= 0) return { mode: "closed", msLeft: 0, sendsAs: "template" }
  return {
    mode: msLeft < 6 * HOUR ? "closing" : "open",
    msLeft,
    sendsAs: "freeform",
  }
}

export function formatCountdown(ms: number): string {
  const h = Math.floor(ms / HOUR)
  const m = Math.floor((ms % HOUR) / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`
}

export function relativeTime(ts: number, now = Date.now()): string {
  const mins = Math.round((now - ts) / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

export function clockTime(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

export function dayLabel(ts: number, now = Date.now()): string {
  const d = new Date(ts)
  const today = new Date(now)
  if (d.toDateString() === today.toDateString()) return "Today"
  const yesterday = new Date(now - 86_400_000)
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday"
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" })
}
