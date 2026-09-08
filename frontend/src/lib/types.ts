// Mirrors the Firestore schema in support-system-design.md §5.
// These enums are closed sets — the API rejects anything outside them.

export type TicketStatus = "open" | "in_progress" | "resolved" | "closed"
export type SlaState = "ok" | "reminder_due" | "breached"
export type Lang = "en" | "hi" | "te" | "ta"
export type ServiceId = "anganwadi-vr" | "german-ai" | "poshan-ai"

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
  contactName: string
  centreName: string
  serviceId: ServiceId
  serviceName: string
  categoryId: string
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
  messages: Message[]
  events: TicketEvent[]
}

export const SERVICES: Record<ServiceId, { name: string; color: string }> = {
  "anganwadi-vr": { name: "Anganwadi VR", color: "#7C5BD4" },
  "poshan-ai": { name: "Poshan AI", color: "#1E8F6B" },
  "german-ai": { name: "German AI", color: "#C2762A" },
}

export const LANGUAGES: Record<Lang, string> = {
  en: "English",
  hi: "हिन्दी",
  te: "తెలుగు",
  ta: "தமிழ்",
}

export const STATUS_LABEL: Record<TicketStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
}

/** Approved Meta templates, one per language. Used once the 24h window closes. */
export const TEMPLATES: Record<Lang, string> = {
  hi: "नमस्ते {{1}}, आपकी शिकायत {{2}} का समाधान हो गया है।\n{{3}}\n— i3w सहायता",
  en: "Hello {{1}}, your report {{2}} has been resolved.\n{{3}}\n— i3w Support",
  te: "నమస్కారం {{1}}, మీ ఫిర్యాదు {{2}} పరిష్కరించబడింది.\n{{3}}\n— i3w సహాయం",
  ta: "வணக்கம் {{1}}, உங்கள் புகார் {{2}} தீர்க்கப்பட்டது.\n{{3}}\n— i3w உதவி",
}

export const WHATSAPP_WINDOW_HOURS = 24
