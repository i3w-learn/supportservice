// Mirrors the Firestore schema in support-system-design.md §5.
// These enums are closed sets — the API rejects anything outside them.

export type TicketStatus = "open" | "in_progress" | "resolved" | "closed"
export type SlaState = "ok" | "reminder_due" | "breached"
export type Lang = "en" | "hi" | "mr" | "bn"
export type CategoryId = "device" | "software" | "other"

export type AttachmentState = "pending" | "stored" | "failed"
export type SentVia = "freeform" | "template"
export type ProviderStatus = "queued" | "sent" | "delivered" | "read" | "failed"

export type EventType =
  | "created"
  | "status_changed"
  | "note"
  | "resolution_sent"
  | "delivered"
  | "sla_flagged"
  | "media_failed"
  | "message_added"

export interface Attachment {
  state: AttachmentState
  mimeType: string
  sizeBytes: number | null
  attempts: number
}

export interface Message {
  messageId: string
  direction: "in" | "out"
  ticketId: string | null
  type: "text" | "image" | "video" | "document" | "interactive"
  text: string | null
  attachment?: Attachment
  sentVia?: SentVia
  providerStatus?: ProviderStatus
  createdAt: number
}

export interface TicketEvent {
  eventId: string
  type: EventType
  from?: TicketStatus
  to?: TicketStatus
  actor: "bot" | "admin" | "system"
  note: string | null
  at: number
}

export interface Resolution {
  text: string
  sentAt: number
  deliveryState: ProviderStatus
  attempts: number
}

export interface Ticket {
  ticketId: string
  waNumber: string
  /** Null unless the contact gave a name in an earlier flow — the template
   *  flow never asks for one. */
  contactName: string | null
  categoryId: CategoryId
  /** The category as the contact saw it, in their own language. */
  categoryLabel: string
  language: Lang
  description: string
  attachmentCount: number
  status: TicketStatus
  slaState: SlaState
  resolution: Resolution | null
  createdAt: number
  updatedAt: number
  firstResponseAt: number | null
  resolvedAt: number | null
  closedAt: number | null
  /** Load-bearing: decides free text vs approved template (§5). */
  lastInboundAt: number
  /** Written when a ticket is reopened — the deadline clock restarts here. */
  slaStartedAt?: number
  /** Optional: these live in subcollections and are hydrated separately. */
  messages?: Message[]
  events?: TicketEvent[]
}

export const CATEGORIES: Record<CategoryId, { name: string; color: string }> = {
  device: { name: "Device", color: "#C2762A" },
  software: { name: "Software", color: "#7C5BD4" },
  other: { name: "Other", color: "#3E8FA8" },
}

/** Tickets from before the template flow carry categories the dashboard no
 *  longer knows (e.g. "controller"). Show those under the label the contact
 *  saw, in a neutral colour, rather than crash the whole page on one row. */
export function categoryMeta(id: string, label?: string): { name: string; color: string } {
  return CATEGORIES[id as CategoryId] ?? { name: label || id, color: "var(--color-muted-foreground)" }
}

export const LANGUAGES: Record<Lang, string> = {
  en: "English",
  hi: "हिन्दी",
  mr: "मराठी",
  bn: "বাংলা",
}

export const STATUS_LABEL: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
}

/** The approved `ticket_resolved` template, one per language. Used once the
 *  24h window closes: {{1}} is the ticket ID, {{2}} the admin's text. */
export const TEMPLATES: Record<Lang, string> = {
  en: 'Hi! 👋 Your support ticket has been resolved.\n\n🎫 Ticket ID: {{1}}\n📋 Resolution: {{2}}\n\nIf you still face any issues, simply send us "Hi" again and we\'ll help you right away.',
  hi: 'नमस्ते! 👋 आपके सपोर्ट टिकट का समाधान हो गया है।\n\n🎫 टिकट ID: {{1}}\n📋 समाधान: {{2}}\n\nअगर आपको अभी भी कोई समस्या है, तो बस हमें फिर से "Hi" भेजें और हम तुरंत आपकी मदद करेंगे।',
  mr: 'नमस्कार! 👋 तुमच्या सपोर्ट तिकिटाचे निराकरण झाले आहे.\n\n🎫 तिकीट ID: {{1}}\n📋 समाधान: {{2}}\n\nतरीही काही अडचण असल्यास, आम्हाला पुन्हा "Hi" पाठवा, आम्ही लगेच मदत करू.',
  bn: 'নমস্কার! 👋 আপনার সাপোর্ট টিকিটের সমাধান হয়েছে।\n\n🎫 টিকিট ID: {{1}}\n📋 সমাধান: {{2}}\n\nএখনও সমস্যা থাকলে আবার "Hi" পাঠান, আমরা সঙ্গে সঙ্গে সাহায্য করব।',
}

export const WHATSAPP_WINDOW_HOURS = 24
