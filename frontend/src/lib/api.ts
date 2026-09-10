// frontend/src/lib/api.ts
import { auth } from "@/firebase"
import type { TicketStatus } from "./types"

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8088"

async function headers(): Promise<Record<string, string>> {
  const token = await auth?.currentUser?.getIdToken()
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function post(path: string, body?: object): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    method: "POST",
    headers: await headers(),
    body: body ? JSON.stringify(body) : undefined,
  })
}

async function patch(path: string, body: object): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: await headers(),
    body: JSON.stringify(body),
  })
}

export const api = {
  changeStatus: (ticketId: string, to: TicketStatus, note?: string) =>
    patch(`/tickets/${ticketId}/status`, { to, note }),

  resolve: (ticketId: string, text: string) =>
    post(`/tickets/${ticketId}/resolution`, { text }),

  addNote: (ticketId: string, text: string) =>
    post(`/tickets/${ticketId}/notes`, { text }),

  resend: (ticketId: string) =>
    post(`/tickets/${ticketId}/resend`),

  getAttachmentUrl: async (messageId: string): Promise<string | null> => {
    const res = await fetch(`${BASE}/attachments/${messageId}/url`, {
      headers: await headers(),
    })
    if (!res.ok) return null
    const data = await res.json()
    return data.url ?? null
  },
}
