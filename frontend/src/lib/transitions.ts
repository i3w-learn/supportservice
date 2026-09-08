import type { TicketStatus } from "./types"

/**
 * The legal transition table from §8. Anything not listed here returns 409 on
 * the API, so the board must refuse it too rather than let a card move and
 * then snap back.
 */
const LEGAL: Record<TicketStatus, TicketStatus[]> = {
  open: ["in_progress", "resolved"],
  in_progress: ["open", "resolved"],
  resolved: ["in_progress"],
  closed: [],
}

export type TransitionCheck =
  | { ok: true; needsResolution: boolean }
  | { ok: false; reason: string }

export function checkTransition(from: TicketStatus, to: TicketStatus): TransitionCheck {
  if (from === to) return { ok: true, needsResolution: false }

  if (to === "closed") {
    return {
      ok: false,
      reason: "Only a delivery receipt closes a ticket — you cannot close it by hand.",
    }
  }

  if (from === "closed") {
    return {
      ok: false,
      reason: "A closed ticket reopens only when the contact writes back within 7 days.",
    }
  }

  if (!LEGAL[from].includes(to)) {
    return { ok: false, reason: `${from} → ${to} is not a legal transition.` }
  }

  // Resolving sends a WhatsApp message, so it needs text — a drag alone is not enough.
  return { ok: true, needsResolution: to === "resolved" }
}
