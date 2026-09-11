// frontend/src/lib/firestore.ts
import {
  collection,
  collectionGroup,
  onSnapshot,
  orderBy,
  query,
  Timestamp,
  where,
} from "firebase/firestore"
import type { QueryDocumentSnapshot, Unsubscribe } from "firebase/firestore"
import { useEffect, useState } from "react"

import { db, isFirebaseConfigured } from "@/firebase"
import { MOCK_TICKETS } from "./mock"
import type { Message, Ticket, TicketEvent } from "./types"

// The backend writes datetimes, which Firestore hands back as Timestamp
// objects. Everything downstream (types.ts, window.ts) works in epoch ms.
function toPlain(value: unknown): unknown {
  if (value instanceof Timestamp) return value.toMillis()
  if (Array.isArray(value)) return value.map(toPlain)
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toPlain(v)]))
  }
  return value
}

function plainData(snap: QueryDocumentSnapshot): Record<string, unknown> {
  return toPlain(snap.data()) as Record<string, unknown>
}

export function useTickets(): { tickets: Ticket[]; loading: boolean } {
  const [tickets, setTickets] = useState<Ticket[]>(isFirebaseConfigured ? [] : MOCK_TICKETS)
  const [loading, setLoading] = useState(isFirebaseConfigured)

  useEffect(() => {
    if (!isFirebaseConfigured || !db) return

    const q = query(collection(db, "tickets"), orderBy("createdAt", "desc"))
    const unsub = onSnapshot(
      q,
      (snap) => {
        const docs = snap.docs.map((doc) => ({
          ticketId: doc.id,
          ...plainData(doc),
          messages: [],
          events: [],
        })) as unknown as Ticket[]
        setTickets(docs)
        setLoading(false)
      },
      (err) => {
        console.error("tickets listener error:", err)
        setLoading(false)
      },
    )
    return unsub
  }, [])

  return { tickets, loading }
}

export function useTicketDetail(ticketId: string | null): {
  messages: Message[]
  events: TicketEvent[]
} {
  const [messages, setMessages] = useState<Message[]>([])
  const [events, setEvents] = useState<TicketEvent[]>([])

  useEffect(() => {
    if (!ticketId || !isFirebaseConfigured || !db) {
      setMessages([])
      setEvents([])
      return
    }

    const unsubs: Unsubscribe[] = []

    // Messages are under contacts/{waNumber}/messages, filtered by ticketId.
    // Use a collection group query.
    const msgQ = query(
      collectionGroup(db, "messages"),
      where("ticketId", "==", ticketId),
      orderBy("createdAt", "asc"),
    )
    unsubs.push(
      onSnapshot(
        msgQ,
        (snap) => {
          setMessages(
            snap.docs.map((d) => ({ messageId: d.id, ...plainData(d) }) as unknown as Message),
          )
        },
        (err) => console.error("messages listener error:", err),
      ),
    )

    // Events are under tickets/{ticketId}/events
    const evtQ = query(
      collection(db, "tickets", ticketId, "events"),
      orderBy("at", "asc"),
    )
    unsubs.push(
      onSnapshot(
        evtQ,
        (snap) => {
          setEvents(
            snap.docs.map((d) => ({ eventId: d.id, ...plainData(d) }) as unknown as TicketEvent),
          )
        },
        (err) => console.error("events listener error:", err),
      ),
    )

    return () => unsubs.forEach((u) => u())
  }, [ticketId])

  return { messages, events }
}
