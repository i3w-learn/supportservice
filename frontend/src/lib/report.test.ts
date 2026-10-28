import { describe, expect, it } from "vitest"

import { byBlock, byCentre, UNPLACED } from "./report"
import type { CentreRef, Ticket } from "./types"

const SAVNER: CentreRef = {
  centreId: "NGP-AWC-017",
  block: "सावनेर",
  blockEn: "Savner",
  village: "टेकाडी",
  villageEn: "Tekadi",
}
const KATOL: CentreRef = {
  centreId: "NGP-AWC-006",
  block: "काटोल",
  blockEn: "Katol",
  village: "खानगाव",
  villageEn: "Khangaon",
}

function ticket(overrides: Partial<Ticket>): Ticket {
  return {
    ticketId: "TKT-1",
    waNumber: "919876543210",
    contactName: null,
    categoryId: "device",
    categoryLabel: "Device",
    language: "mr",
    description: "",
    attachmentCount: 0,
    status: "open",
    slaState: "ok",
    resolution: null,
    createdAt: 0,
    updatedAt: 0,
    firstResponseAt: null,
    resolvedAt: null,
    closedAt: null,
    lastInboundAt: 0,
    ...overrides,
  }
}

describe("byBlock", () => {
  it("counts tickets per block, busiest first, by status and category", () => {
    const rows = byBlock([
      ticket({ centre: SAVNER, status: "open" }),
      ticket({ centre: SAVNER, status: "closed", categoryId: "software" }),
      ticket({ centre: KATOL, status: "in_progress" }),
    ])

    expect(rows.map((r) => r.label)).toEqual(["Savner", "Katol"])
    expect(rows[0].total).toBe(2)
    expect(rows[0].byStatus).toEqual({ open: 1, in_progress: 0, resolved: 0, closed: 1 })
    expect(rows[0].byCategory).toEqual({ device: 1, software: 1, other: 0 })
    expect(rows[0].sublabel).toBe("सावनेर")
  })

  it("keeps tickets without a centre in a last row so totals add up", () => {
    const rows = byBlock([ticket({}), ticket({ centre: KATOL }), ticket({ centre: null })])

    expect(rows.map((r) => r.key)).toEqual(["Katol", UNPLACED])
    expect(rows[1].total).toBe(2)
  })

  it("files a legacy category under other", () => {
    const rows = byBlock([ticket({ centre: KATOL, categoryId: "controller" as never })])

    expect(rows[0].byCategory.other).toBe(1)
  })
})

describe("byCentre", () => {
  it("labels each centre by village, block and id", () => {
    const rows = byCentre([ticket({ centre: SAVNER }), ticket({ centre: SAVNER })])

    expect(rows).toHaveLength(1)
    expect(rows[0].label).toBe("Tekadi · Savner")
    expect(rows[0].sublabel).toBe("टेकाडी · NGP-AWC-017")
    expect(rows[0].total).toBe(2)
  })
})
