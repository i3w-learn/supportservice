import { describe, expect, it } from "vitest"

import { CATEGORIES, categoryMeta } from "./types"

describe("categoryMeta — tickets from the old bot flow", () => {
  it("returns the known entry for a current category", () => {
    expect(categoryMeta("device", "डिवाइस")).toBe(CATEGORIES.device)
  })

  it("falls back to the contact-facing label for a category the dashboard no longer knows", () => {
    const meta = categoryMeta("controller", "Controller")
    expect(meta.name).toBe("Controller")
    expect(meta.color).toBeTruthy()
  })

  it("falls back to the raw id when there is no label either", () => {
    expect(categoryMeta("controller").name).toBe("controller")
  })
})
