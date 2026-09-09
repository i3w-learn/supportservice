import { describe, expect, it } from "vitest"

import { checkTransition } from "./transitions"
import type { TicketStatus } from "./types"

const ALL: TicketStatus[] = ["open", "in_progress", "resolved", "closed"]

describe("checkTransition — the §8 table", () => {
  it("allows the four moves an admin is meant to make", () => {
    expect(checkTransition("open", "in_progress").ok).toBe(true)
    expect(checkTransition("in_progress", "open").ok).toBe(true)
    expect(checkTransition("open", "resolved").ok).toBe(true)
    expect(checkTransition("in_progress", "resolved").ok).toBe(true)
  })

  it("lets a permanently failed send go back to in progress", () => {
    expect(checkTransition("resolved", "in_progress").ok).toBe(true)
  })

  it("requires a written resolution before resolving", () => {
    const check = checkTransition("in_progress", "resolved")
    expect(check).toEqual({ ok: true, needsResolution: true })
  })

  it("does not ask for a resolution on any other move", () => {
    expect(checkTransition("open", "in_progress")).toEqual({ ok: true, needsResolution: false })
  })

  describe("closing is the delivery receipt's job, never the admin's", () => {
    it.each(ALL)("refuses %s → closed", (from) => {
      if (from === "closed") return
      const check = checkTransition(from, "closed")
      expect(check.ok).toBe(false)
      expect(check.ok === false && check.reason).toMatch(/delivery receipt/i)
    })
  })

  describe("a closed ticket reopens only when the contact writes back", () => {
    it.each(ALL)("refuses closed → %s", (to) => {
      if (to === "closed") return
      const check = checkTransition("closed", to)
      expect(check.ok).toBe(false)
      expect(check.ok === false && check.reason).toMatch(/writes back/i)
    })
  })

  it("refuses resolved → open, which is not in the table", () => {
    expect(checkTransition("resolved", "open").ok).toBe(false)
  })

  it("treats a move to the same column as a no-op, not an error", () => {
    for (const status of ALL) {
      expect(checkTransition(status, status)).toEqual({ ok: true, needsResolution: false })
    }
  })
})
