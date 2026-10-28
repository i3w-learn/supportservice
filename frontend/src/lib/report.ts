// Counts for the Report view: tickets grouped by block and by centre, split
// by status. Pure, so it is unit-tested; the dashboard already holds every
// ticket in memory, so no query is needed.
import type { CategoryId, Ticket, TicketStatus } from "./types"

export const UNPLACED = "— no centre —"

export interface ReportRow {
  key: string
  label: string
  sublabel?: string
  total: number
  byStatus: Record<TicketStatus, number>
  byCategory: Record<CategoryId | "other", number>
}

function emptyRow(key: string, label: string, sublabel?: string): ReportRow {
  return {
    key,
    label,
    sublabel,
    total: 0,
    byStatus: { open: 0, in_progress: 0, resolved: 0, closed: 0 },
    byCategory: { device: 0, software: 0, other: 0 },
  }
}

function tally(row: ReportRow, ticket: Ticket): void {
  row.total += 1
  row.byStatus[ticket.status] += 1
  const category = ticket.categoryId in row.byCategory ? ticket.categoryId : "other"
  row.byCategory[category] += 1
}

/** One row per block, English name, busiest first. Tickets without a centre
 *  land in a final "no centre" row so the totals still add up. */
export function byBlock(tickets: Ticket[]): ReportRow[] {
  const rows = new Map<string, ReportRow>()
  for (const t of tickets) {
    const key = t.centre?.blockEn ?? UNPLACED
    const row = rows.get(key) ?? emptyRow(key, key, t.centre?.block)
    tally(row, t)
    rows.set(key, row)
  }
  return sorted(rows)
}

/** One row per centre, labelled by village and id. */
export function byCentre(tickets: Ticket[]): ReportRow[] {
  const rows = new Map<string, ReportRow>()
  for (const t of tickets) {
    const key = t.centre?.centreId ?? UNPLACED
    const row =
      rows.get(key) ??
      emptyRow(
        key,
        t.centre ? `${t.centre.villageEn} · ${t.centre.blockEn}` : UNPLACED,
        t.centre ? `${t.centre.village} · ${t.centre.centreId}` : undefined,
      )
    tally(row, t)
    rows.set(key, row)
  }
  return sorted(rows)
}

function sorted(rows: Map<string, ReportRow>): ReportRow[] {
  return [...rows.values()].sort((a, b) => {
    if (a.key === UNPLACED) return 1
    if (b.key === UNPLACED) return -1
    return b.total - a.total || a.label.localeCompare(b.label)
  })
}
