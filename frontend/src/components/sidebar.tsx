import { AlertTriangle, BarChart3, LayoutGrid } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import { CATEGORIES } from "@/lib/types"
import type { CategoryId, Ticket } from "@/lib/types"

export type ViewKey = "all" | "attention" | "report"

/** The block filter's "no centre" bucket: tickets that came in without a QR scan. */
export const NO_BLOCK = "__none__"

export function needsAttention(t: Ticket): boolean {
  return t.slaState !== "ok" || t.resolution?.deliveryState === "failed"
}

const VIEWS: { key: ViewKey; label: string; Icon: typeof LayoutGrid }[] = [
  { key: "all", label: "All tickets", Icon: LayoutGrid },
  { key: "attention", label: "Needs attention", Icon: AlertTriangle },
  { key: "report", label: "Report", Icon: BarChart3 },
]

interface Props {
  tickets: Ticket[]
  view: ViewKey
  category: CategoryId | "all"
  block: string | "all"
  onView: (key: ViewKey) => void
  onCategory: (id: CategoryId | "all") => void
  onBlock: (block: string | "all") => void
}

export function blockOf(t: Ticket): string {
  return t.centre?.blockEn || NO_BLOCK
}

export function Sidebar({ tickets, view, category, block, onView, onCategory, onBlock }: Props) {
  const inCategory = (t: Ticket) => category === "all" || t.categoryId === category

  // Blocks come from the tickets themselves, so a block appears once its
  // first ticket does and the list never needs maintaining.
  const blocks = [...new Set(tickets.map(blockOf))].sort((a, b) =>
    a === NO_BLOCK ? 1 : b === NO_BLOCK ? -1 : a.localeCompare(b),
  )

  return (
    <nav className="flex w-52 shrink-0 flex-col gap-5 overflow-y-auto border-r px-2.5 py-4">
      <div className="flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          Views
        </p>
        {VIEWS.map(({ key, label, Icon }) => {
          const count =
            key === "report"
              ? null
              : key === "attention"
                ? tickets.filter((t) => needsAttention(t) && inCategory(t)).length
                : tickets.filter(inCategory).length
          const active = view === key
          return (
            <Button
              key={key}
              variant="ghost"
              onClick={() => onView(key)}
              aria-pressed={active}
              className={cn(
                "h-8 justify-start gap-2 px-2 font-normal",
                active && "bg-accent font-medium text-accent-foreground dark:bg-white/[0.08]",
              )}
            >
              <Icon
                className={cn(
                  "size-3.5",
                  key === "attention" && (count ?? 0) > 0
                    ? "text-red-500"
                    : "text-muted-foreground",
                )}
              />
              <span className="truncate">{label}</span>
              {count !== null && (
                <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">
                  {count}
                </span>
              )}
            </Button>
          )
        })}
      </div>

      <Separator />

      <div className="flex flex-col gap-0.5">
        <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          Category
        </p>
        {(
          [
            ["all", "All categories"],
            ...Object.entries(CATEGORIES).map(([id, c]) => [id, c.name] as const),
          ] as [CategoryId | "all", string][]
        ).map(([id, label]) => {
          const active = category === id
          const count =
            id === "all" ? tickets.length : tickets.filter((t) => t.categoryId === id).length
          return (
            <Button
              key={id}
              variant="ghost"
              onClick={() => onCategory(id)}
              aria-pressed={active}
              className={cn(
                "h-8 justify-start gap-2 px-2 font-normal",
                active && "bg-accent font-medium text-accent-foreground dark:bg-white/[0.08]",
              )}
            >
              <span
                className="size-2 shrink-0 rounded-[2px]"
                style={{
                  background:
                    id === "all"
                      ? "var(--color-muted-foreground)"
                      : CATEGORIES[id as CategoryId].color,
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

      {blocks.length > 0 && (
        <>
          <Separator />

          <div className="flex flex-col gap-0.5">
            <p className="px-2 pb-1.5 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              Block
            </p>
            {(["all", ...blocks] as string[]).map((key) => {
              const active = block === key
              const count =
                key === "all" ? tickets.length : tickets.filter((t) => blockOf(t) === key).length
              const label = key === "all" ? "All blocks" : key === NO_BLOCK ? "No centre" : key
              return (
                <Button
                  key={key}
                  variant="ghost"
                  onClick={() => onBlock(key)}
                  aria-pressed={active}
                  className={cn(
                    "h-8 justify-start gap-2 px-2 font-normal",
                    key === NO_BLOCK && "text-muted-foreground",
                    active && "bg-accent font-medium text-accent-foreground dark:bg-white/[0.08]",
                  )}
                >
                  <span className="truncate">{label}</span>
                  <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">
                    {count}
                  </span>
                </Button>
              )
            })}
          </div>
        </>
      )}

      <p className="mt-auto rounded-md bg-muted px-2.5 py-2 text-[11px] leading-relaxed text-muted-foreground">
        There is no email in this system.{" "}
        <span className="font-medium text-foreground">Needs attention is the alert.</span>
      </p>
    </nav>
  )
}
