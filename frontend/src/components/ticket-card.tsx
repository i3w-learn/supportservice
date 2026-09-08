import { useEffect, useRef, useState } from "react"
import { draggable } from "@atlaskit/pragmatic-drag-and-drop/element/adapter"
import { AlertTriangle, Clock3, Paperclip, TriangleAlert } from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { SERVICES } from "@/lib/types"
import type { Ticket } from "@/lib/types"
import { replyWindow } from "@/lib/window"

function initials(name: string): string {
  return name
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase()
}

export function TicketCard({
  ticket,
  onOpen,
}: {
  ticket: Ticket
  onOpen: (id: string) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  const service = SERVICES[ticket.serviceId]
  const win = replyWindow(ticket.lastInboundAt)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    return draggable({
      element,
      getInitialData: () => ({ ticketId: ticket.ticketId, from: ticket.status }),
      onDragStart: () => setDragging(true),
      onDrop: () => setDragging(false),
    })
  }, [ticket.ticketId, ticket.status])

  return (
    <div
      ref={ref}
      role="button"
      tabIndex={0}
      onClick={() => onOpen(ticket.ticketId)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onOpen(ticket.ticketId)
        }
      }}
      className={cn(
        "group cursor-pointer rounded border border-transparent bg-card px-3 py-2.5 text-left shadow-xs transition-shadow",
        "hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        dragging && "opacity-40",
      )}
    >
      <p className="text-[13px] leading-snug text-foreground">{ticket.categoryLabel}</p>

      <div className="mt-3 flex items-center gap-2">
        <span
          className="size-3.5 shrink-0 rounded-[3px]"
          style={{ background: service.color }}
          title={service.name}
          aria-label={service.name}
        />
        <span className="font-mono text-[11px] tracking-tight text-muted-foreground">
          {ticket.ticketId.replace("TKT-", "")}
        </span>

        <div className="ml-auto flex items-center gap-1.5">
          {ticket.attachmentCount > 0 && (
            <span className="flex items-center gap-0.5 text-[11px] text-muted-foreground">
              <Paperclip className="size-3" />
              {ticket.attachmentCount}
            </span>
          )}

          {ticket.slaState !== "ok" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <TriangleAlert
                  className={cn(
                    "size-3.5",
                    ticket.slaState === "breached" ? "text-red-500" : "text-amber-500",
                  )}
                />
              </TooltipTrigger>
              <TooltipContent>
                {ticket.slaState === "breached"
                  ? "48h with no first response"
                  : "24h with no first response"}
              </TooltipContent>
            </Tooltip>
          )}

          {win.mode === "closed" && ticket.status !== "closed" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Clock3 className="size-3.5 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent>24h window closed — template only</TooltipContent>
            </Tooltip>
          )}

          {ticket.resolution?.deliveryState === "failed" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <AlertTriangle className="size-3.5 text-red-500" />
              </TooltipTrigger>
              <TooltipContent>Resolution send failed</TooltipContent>
            </Tooltip>
          )}

          <Tooltip>
            <TooltipTrigger asChild>
              <Avatar className="size-5">
                <AvatarFallback className="text-[9px] font-medium">
                  {initials(ticket.contactName)}
                </AvatarFallback>
              </Avatar>
            </TooltipTrigger>
            <TooltipContent>
              {ticket.contactName} · {ticket.centreName}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  )
}
