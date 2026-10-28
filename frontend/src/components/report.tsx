import { useState } from "react"

import { byBlock, byCentre } from "@/lib/report"
import type { ReportRow } from "@/lib/report"
import { cn } from "@/lib/utils"
import { CATEGORIES, STATUS_LABEL } from "@/lib/types"
import type { Ticket, TicketStatus } from "@/lib/types"

const STATUSES: TicketStatus[] = ["open", "in_progress", "resolved", "closed"]

/** Tickets per block and per centre. Everything the board already holds,
 *  so it is a pure regrouping — no query, always current. */
export function Report({ tickets }: { tickets: Ticket[] }) {
  const [grouping, setGrouping] = useState<"block" | "centre">("block")
  const rows = grouping === "block" ? byBlock(tickets) : byCentre(tickets)

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto px-6 pb-6">
      <div className="flex items-center gap-1 text-sm">
        {(["block", "centre"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setGrouping(key)}
            aria-pressed={grouping === key}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium",
              grouping === key ? "bg-accent text-accent-foreground" : "text-muted-foreground",
            )}
          >
            By {key}
          </button>
        ))}
        <span className="ml-auto text-xs text-muted-foreground">
          {tickets.length} tickets · {rows.length} {grouping === "block" ? "blocks" : "centres"}
        </span>
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left text-[10px] uppercase tracking-widest text-muted-foreground">
            <th className="py-2 pr-3 font-medium">{grouping === "block" ? "Block" : "Centre"}</th>
            <th className="py-2 pr-3 text-right font-medium">Total</th>
            {STATUSES.map((s) => (
              <th key={s} className="py-2 pr-3 text-right font-medium">
                {STATUS_LABEL[s]}
              </th>
            ))}
            {Object.entries(CATEGORIES).map(([id, c]) => (
              <th key={id} className="py-2 pr-3 text-right font-medium">
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <ReportLine key={row.key} row={row} />
          ))}
        </tbody>
      </table>

      {rows.length === 0 && (
        <p className="text-sm text-muted-foreground">No tickets yet.</p>
      )}
    </div>
  )
}

function ReportLine({ row }: { row: ReportRow }) {
  return (
    <tr className="border-b border-border/60">
      <td className="py-2 pr-3">
        <span className="font-medium">{row.label}</span>
        {row.sublabel && (
          <span className="ml-2 text-xs text-muted-foreground">{row.sublabel}</span>
        )}
      </td>
      <Cell value={row.total} strong />
      {STATUSES.map((s) => (
        <Cell key={s} value={row.byStatus[s]} />
      ))}
      {Object.keys(CATEGORIES).map((id) => (
        <Cell key={id} value={row.byCategory[id as keyof typeof row.byCategory]} />
      ))}
    </tr>
  )
}

function Cell({ value, strong = false }: { value: number; strong?: boolean }) {
  return (
    <td
      className={cn(
        "py-2 pr-3 text-right font-mono tabular-nums",
        value === 0 ? "text-muted-foreground/50" : strong ? "font-semibold" : "",
      )}
    >
      {value}
    </td>
  )
}
