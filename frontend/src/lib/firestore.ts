// frontend/src/lib/firestore.ts
import {
  collection,
  collectionGroup,
  onSnapshot,
  orderBy,
  query,
  where,
} from "firebase/firestore"
import type { Unsubscribe } from "firebase/firestore"
import { useEffect, useState } from "react"

import { db, isFirebaseConfigured } from "@/firebase"
import { MOCK_TICKETS } from "./mock"
import type { Message, Ticket, TicketEvent } from "./types"

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
          ...doc.data(),
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
      onSnapshot(msgQ, (snap) => {
        setMessages(snap.docs.map((d) => ({ messageId: d.id, ...d.data() }) as Message))
      }),
    )

    // Events are under tickets/{ticketId}/events
    const evtQ = query(
      collection(db, "tickets", ticketId, "events"),
      orderBy("at", "asc"),
    )
    unsubs.push(
      onSnapshot(evtQ, (snap) => {
        setEvents(snap.docs.map((d) => ({ eventId: d.id, ...d.data() }) as TicketEvent))
      }),
    )

    return () => unsubs.forEach((u) => u())
  }, [ticketId])

  return { messages, events }
}
