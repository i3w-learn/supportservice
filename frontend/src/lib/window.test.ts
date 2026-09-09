import { describe, expect, it } from "vitest"

import { formatCountdown, relativeTime, replyWindow } from "./window"

const HOUR = 3_600_000
const NOW = Date.UTC(2026, 8, 9, 12, 0, 0)

describe("replyWindow — the 24-hour rule", () => {
  it("allows free text just inside 24 hours", () => {
    const win = replyWindow(NOW - 23.9 * HOUR, NOW)
    expect(win.sendsAs).toBe("freeform")
    expect(win.mode).toBe("closing")
  })

  it("forces a template just outside 24 hours", () => {
    const win = replyWindow(NOW - 24.1 * HOUR, NOW)
    expect(win.sendsAs).toBe("template")
    expect(win.mode).toBe("closed")
    expect(win.msLeft).toBe(0)
  })

  it("closes exactly at the boundary, not a millisecond later", () => {
    expect(replyWindow(NOW - 24 * HOUR, NOW).mode).toBe("closed")
    expect(replyWindow(NOW - 24 * HOUR + 1, NOW).mode).toBe("closing")
  })

  it("warns in the last six hours so the admin can act before it shuts", () => {
    expect(replyWindow(NOW - 17.9 * HOUR, NOW).mode).toBe("open")
    expect(replyWindow(NOW - 18.1 * HOUR, NOW).mode).toBe("closing")
  })

  it("reports the time actually remaining", () => {
    expect(replyWindow(NOW - 20 * HOUR, NOW).msLeft).toBe(4 * HOUR)
  })

  it("never reports negative time left", () => {
    expect(replyWindow(NOW - 100 * HOUR, NOW).msLeft).toBe(0)
  })
})

describe("formatCountdown", () => {
  it("pads minutes and seconds so the digits do not jump", () => {
    expect(formatCountdown(4 * HOUR + 5 * 60_000 + 3000)).toBe("4h 05m 03s")
  })

  it("handles zero", () => {
    expect(formatCountdown(0)).toBe("0h 00m 00s")
  })
})

describe("relativeTime", () => {
  it.each([
    [30_000, "just now"],
    [5 * 60_000, "5m ago"],
    [3 * HOUR, "3h ago"],
    [50 * HOUR, "2d ago"],
  ])("renders %i ms ago as %s", (delta, expected) => {
    expect(relativeTime(NOW - delta, NOW)).toBe(expected)
  })
})
