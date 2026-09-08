import { AlertTriangle, CheckCircle2, CircleDot, Clock, Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import { SERVICES } from "@/lib/types"
import type { ServiceId, Ticket } from "@/lib/types"

export type QueueKey = "attention" | "open" | "in_progress" | "resolved" | "closed"

export const QUEUES: {
  key: QueueKey
  label: string
  Icon: typeof CircleDot
  match: (t: Ticket) => boolean
}[] = [
  {
    key: "attention",
    label: "Needs attention",
    Icon: AlertTriangle,
    // No email exists (§12), so this queue is the entire alerting system.
    match: (t) => t.slaState !== "ok" || t.resolution?.deliveryState === "failed",
  },
  { key: "open", label: "Open", Icon: CircleDot, match: (t) => t.status === "open" },
  { key: "in_progress", label: "In progress", Icon: Clock, match: (t) => t.status === "in_progress" },
  { key: "resolved", label: "Awaiting delivery", Icon: Send, match: (t) => t.status === "resolved" },
  { key: "closed", label: "Closed", Icon: CheckCircle2, match: (t) => t.status === "closed" },
]

interface Props {
  tickets: Ticket[]
  queue: QueueKey
  service: ServiceId | "all"
  onQueue: (key: QueueKey) => void
  onService: (id: ServiceId | "all") => void
}

export function QueueSidebar({ tickets, queue, service, onQueue, onService }: Props) {
  const inService = (t: Ticket) => service === "all" || t.serviceId === service

  return (
    <nav className="flex h-full w-56 shrink-0 flex-col gap-5 overflow-y-auto border-r bg-sidebar p-3">
      <div className="flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          Queues
        </p>
        {QUEUES.map(({ key, label, Icon, match }) => {
          const count = tickets.filter((t) => match(t) && inService(t)).length
          const active = queue === key
          return (
            <Button
              key={key}
              variant="ghost"
              onClick={() => onQueue(key)}
              aria-pressed={active}
              className={cn(
                "h-8 justify-start gap-2 px-2 font-normal",
                active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
              )}
            >
              <Icon
                className={cn(
                  "size-3.5",
                  key === "attention" && count > 0 ? "text-red-500" : "text-muted-foreground",
                )}
              />
              <span className="truncate">{label}</span>
              <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">
                {count}
              </span>
            </Button>
          )
        })}
      </div>

      <Separator />

      <div className="flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          Product
        </p>
        {([["all", "All products"], ...Object.entries(SERVICES).map(
          ([id, s]) => [id, s.name] as const,
        )] as [ServiceId | "all", string][]).map(([id, label]) => {
          const active = service === id
          return (
            <Button
              key={id}
              variant="ghost"
              onClick={() => onService(id)}
              aria-pressed={active}
              className={cn(
                "h-8 justify-start gap-2 px-2 font-normal",
                active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
              )}
            >
              <span
                className="size-1.5 shrink-0 rounded-full"
                style={{ background: id === "all" ? "var(--muted-foreground)" : SERVICES[id as ServiceId].color }}
                aria-hidden
              />
              <span className="truncate">{label}</span>
            </Button>
          )
        })}
      </div>

      <p className="mt-auto rounded-md bg-muted p-2.5 text-xs leading-relaxed text-muted-foreground">
        There is no email in this system.{" "}
        <span className="font-medium text-foreground">This queue is the alert.</span> SLA
        breaches and failed sends surface here or nowhere.
      </p>
    </nav>
  )
}
