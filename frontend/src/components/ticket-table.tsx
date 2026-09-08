import { useMemo, useState } from "react"
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import type { ColumnDef, SortingState } from "@tanstack/react-table"
import { ArrowDown, ArrowUp, ChevronsUpDown, Paperclip, Search } from "lucide-react"

import { FailedLozenge, ServiceTag, SlaLozenge, StatusLozenge } from "@/components/lozenge"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { SERVICES } from "@/lib/types"
import type { Ticket } from "@/lib/types"
import { relativeTime } from "@/lib/window"

interface ColumnMeta {
  className?: string
}

interface Props {
  tickets: Ticket[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function TicketTable({ tickets, selectedId, onSelect }: Props) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "updatedAt", desc: true }])
  const [query, setQuery] = useState("")

  const columns = useMemo<ColumnDef<Ticket>[]>(
    () => [
      {
        accessorKey: "ticketId",
        header: "Key",
        cell: ({ row }) => (
          <span className="font-mono text-xs text-muted-foreground">
            {row.original.ticketId.replace("TKT-", "")}
          </span>
        ),
      },
      {
        accessorKey: "description",
        header: "Summary",
        cell: ({ row }) => {
          const t = row.original
          return (
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="truncate font-medium">{t.categoryLabel}</span>
                {t.attachmentCount > 0 && (
                  <span className="flex shrink-0 items-center gap-0.5 text-xs text-muted-foreground">
                    <Paperclip className="size-3" />
                    {t.attachmentCount}
                  </span>
                )}
              </div>
              <span className="line-clamp-1 text-xs text-muted-foreground">{t.description}</span>
              <ServiceTag name={t.serviceName} color={SERVICES[t.serviceId].color} />
            </div>
          )
        },
      },
      {
        accessorKey: "contactName",
        header: "Reporter",
        meta: { className: "hidden xl:table-cell" },
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-sm">{row.original.contactName}</span>
            <span className="truncate text-xs text-muted-foreground">
              {row.original.centreName}
            </span>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <div className="flex flex-col items-start gap-1">
            <StatusLozenge status={row.original.status} />
            <SlaLozenge sla={row.original.slaState} />
            {row.original.resolution?.deliveryState === "failed" && <FailedLozenge />}
          </div>
        ),
      },
      {
        accessorKey: "updatedAt",
        header: "Updated",
        meta: { className: "hidden lg:table-cell" },
        cell: ({ row }) => (
          <span className="whitespace-nowrap font-mono text-xs tabular-nums text-muted-foreground">
            {relativeTime(row.original.updatedAt)}
          </span>
        ),
      },
    ],
    [],
  )

  const table = useReactTable({
    data: tickets,
    columns,
    state: { sorting, globalFilter: query },
    onSortingChange: setSorting,
    onGlobalFilterChange: setQuery,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    globalFilterFn: (row, _columnId, value: string) => {
      const t = row.original as Ticket
      const hay =
        `${t.ticketId} ${t.contactName} ${t.centreName} ${t.categoryLabel} ${t.description} ${t.serviceName}`.toLowerCase()
      return hay.includes(value.toLowerCase())
    },
    getRowId: (row) => row.ticketId,
  })

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by name, centre, or summary"
            className="h-8 pl-8 text-sm"
          />
        </div>
        <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
          {table.getRowModel().rows.length} of {tickets.length}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 z-10 bg-background">
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id} className="hover:bg-transparent">
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted()
                  return (
                    <TableHead
                      key={header.id}
                      className={cn("h-9", (header.column.columnDef.meta as ColumnMeta)?.className)}
                    >
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide hover:text-foreground"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === "asc" ? (
                          <ArrowUp className="size-3" />
                        ) : sorted === "desc" ? (
                          <ArrowDown className="size-3" />
                        ) : (
                          <ChevronsUpDown className="size-3 opacity-35" />
                        )}
                      </button>
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-28 text-center text-muted-foreground">
                  Nothing here. That is the good outcome.
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  onClick={() => onSelect(row.original.ticketId)}
                  data-state={row.original.ticketId === selectedId ? "selected" : undefined}
                  className={cn(
                    "cursor-pointer border-l-2 border-l-transparent",
                    row.original.slaState === "breached" && "border-l-red-500",
                    row.original.slaState === "reminder_due" && "border-l-amber-500",
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn("py-2.5 align-top", (cell.column.columnDef.meta as ColumnMeta)?.className)}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
