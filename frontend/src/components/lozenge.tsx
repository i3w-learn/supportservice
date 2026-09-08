import { cn } from "@/lib/utils"
import { STATUS_LABEL } from "@/lib/types"
import type { SlaState, TicketStatus } from "@/lib/types"

// Jira calls these lozenges. Status is encoded in colour and shape so the
// queue reads at a glance, not only by reading the words.
const STATUS_STYLES: Record<TicketStatus, string> = {
  open: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  in_progress: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  resolved: "bg-violet-100 text-violet-800 dark:bg-violet-500/15 dark:text-violet-300",
  closed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
}

const BASE =
  "inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap"

export function StatusLozenge({ status }: { status: TicketStatus }) {
  return <span className={cn(BASE, STATUS_STYLES[status])}>{STATUS_LABEL[status]}</span>
}

export function SlaLozenge({ sla }: { sla: SlaState }) {
  if (sla === "ok") return null
  return (
    <span
      className={cn(
        BASE,
        sla === "breached"
          ? "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300"
          : "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
      )}
    >
      {sla === "breached" ? "SLA breached" : "SLA due"}
    </span>
  )
}

export function FailedLozenge() {
  return (
    <span className={cn(BASE, "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300")}>
      Send failed
    </span>
  )
}

export function ServiceTag({ name, color }: { name: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted-foreground">
      <span className="size-1.5 rounded-full" style={{ background: color }} aria-hidden />
      {name}
    </span>
  )
}
