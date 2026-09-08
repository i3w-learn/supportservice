import { AlertTriangle, LayoutGrid } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import { SERVICES } from "@/lib/types"
import type { ServiceId, Ticket } from "@/lib/types"

export type ViewKey = "all" | "attention"

export function needsAttention(t: Ticket): boolean {
  return t.slaState !== "ok" || t.resolution?.deliveryState === "failed"
}

const VIEWS: { key: ViewKey; label: string; Icon: typeof LayoutGrid }[] = [
  { key: "all", label: "All tickets", Icon: LayoutGrid },
  { key: "attention", label: "Needs attention", Icon: AlertTriangle },
]

interface Props {
  tickets: Ticket[]
  view: ViewKey
  service: ServiceId | "all"
  onView: (key: ViewKey) => void
  onService: (id: ServiceId | "all") => void
}

export function Sidebar({ tickets, view, service, onView, onService }: Props) {
  const inService = (t: Ticket) => service === "all" || t.serviceId === service

  return (
    <nav className="flex w-52 shrink-0 flex-col gap-5 overflow-y-auto border-r px-2.5 py-4">
      <div className="flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          Views
        </p>
        {VIEWS.map(({ key, label, Icon }) => {
          const count =
            key === "attention"
              ? tickets.filter((t) => needsAttention(t) && inService(t)).length
              : tickets.filter(inService).length
          const active = view === key
          return (
            <Button
              key={key}
              variant="ghost"
              onClick={() => onView(key)}
              aria-pressed={active}
              className={cn(
                "h-8 justify-start gap-2 px-2 font-normal",
                active && "bg-accent font-medium text-accent-foreground",
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
        {(
          [
            ["all", "All products"],
            ...Object.entries(SERVICES).map(([id, s]) => [id, s.name] as const),
          ] as [ServiceId | "all", string][]
        ).map(([id, label]) => {
          const active = service === id
          const count =
            id === "all" ? tickets.length : tickets.filter((t) => t.serviceId === id).length
          return (
            <Button
              key={id}
              variant="ghost"
              onClick={() => onService(id)}
              aria-pressed={active}
              className={cn(
                "h-8 justify-start gap-2 px-2 font-normal",
                active && "bg-accent font-medium text-accent-foreground",
              )}
            >
              <span
                className="size-2 shrink-0 rounded-[2px]"
                style={{
                  background:
                    id === "all" ? "var(--color-muted-foreground)" : SERVICES[id as ServiceId].color,
                }}
                aria-hidden
              />
              <span className="truncate">{label}</span>
              <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">
                {count}
              </span>
            </Button>
          )
        })}
      </div>

      <p className="mt-auto rounded-md bg-muted px-2.5 py-2 text-[11px] leading-relaxed text-muted-foreground">
        There is no email in this system.{" "}
        <span className="font-medium text-foreground">Needs attention is the alert.</span>
      </p>
    </nav>
  )
}
