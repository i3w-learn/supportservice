import { useEffect, useRef, useState } from "react"
import { dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter"
import { monitorForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter"

import { TicketCard } from "@/components/ticket-card"
import { cn } from "@/lib/utils"
import { STATUS_LABEL } from "@/lib/types"
import type { Ticket, TicketStatus } from "@/lib/types"

// Columns are the four statuses from §8, in the order work actually moves.
const COLUMNS: { status: TicketStatus; label: string; hint?: string }[] = [
  { status: "open", label: STATUS_LABEL.open },
  { status: "in_progress", label: STATUS_LABEL.in_progress },
  { status: "resolved", label: "Awaiting delivery", hint: "Sent, waiting for the receipt" },
  { status: "closed", label: STATUS_LABEL.closed, hint: "Delivery confirmed" },
]

interface Props {
  tickets: Ticket[]
  onOpen: (id: string) => void
  onMove: (id: string, to: TicketStatus) => void
}

export function Board({ tickets, onOpen, onMove }: Props) {
  useEffect(
    () =>
      monitorForElements({
        onDrop({ source, location }) {
          const target = location.current.dropTargets[0]
          if (!target) return
          const to = target.data.status as TicketStatus
          const id = source.data.ticketId as string
          const from = source.data.from as TicketStatus
          if (to !== from) onMove(id, to)
        },
      }),
    [onMove],
  )

  return (
    <div className="flex h-full gap-3 overflow-x-auto px-6 pb-6">
      {/* Columns grow to share the width, so a wide screen has no dead strip. */}
      {COLUMNS.map((column) => (
        <Column
          key={column.status}
          status={column.status}
          label={column.label}
          hint={column.hint}
          tickets={tickets.filter((t) => t.status === column.status)}
          onOpen={onOpen}
        />
      ))}
    </div>
  )
}

function Column({
  status,
  label,
  hint,
  tickets,
  onOpen,
}: {
  status: TicketStatus
  label: string
  hint?: string
  tickets: Ticket[]
  onOpen: (id: string) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [over, setOver] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    return dropTargetForElements({
      element,
      getData: () => ({ status }),
      onDragEnter: () => setOver(true),
      onDragLeave: () => setOver(false),
      onDrop: () => setOver(false),
    })
  }, [status])

  return (
    <section
      ref={ref}
      className={cn(
        "flex min-w-64 max-w-[26rem] flex-1 flex-col rounded-md transition-colors",
        // Not `neutral-900` in dark: that is the same value as `card`, so the
        // cards would disappear into the column. Lift the column off the page
        // ground just enough to read as a well, and let the card sit above it.
        "bg-neutral-100 dark:bg-white/[0.035]",
        over && "bg-primary/10 ring-1 ring-primary/30",
      )}
    >
      <header className="flex items-baseline gap-2 px-3 pb-2 pt-3.5">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </h2>
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
          {tickets.length}
        </span>
      </header>

      {hint && (
        <p className="px-3 pb-1 text-[11px] leading-snug text-muted-foreground/80">{hint}</p>
      )}

      <div className="flex min-h-24 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2">
        {tickets.map((ticket) => (
          <TicketCard key={ticket.ticketId} ticket={ticket} onOpen={onOpen} />
        ))}
      </div>
    </section>
  )
}
