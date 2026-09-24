import { describe, expect, it } from "vitest";

import { buildQuery } from "../../lib/api";
import { filterResources } from "../../lib/filters";
import { dueInDays, statusLabel } from "../../lib/legal";

describe("transformări și filtre GovLegal", () => {
  it("construiește query string doar din filtre active", () => {
    expect(buildQuery({ court: "Tribunal", status: "", date_from: null })).toBe("?court=Tribunal");
  });

  it("filtrează diacritice și statusuri", () => {
    const items = [
      { id: "1", title: "Soluționare cerere", status: "OPEN" },
      { id: "2", title: "Plată debit", status: "COMPLETED" },
    ];
    expect(filterResources(items, "soluționare", "OPEN")).toEqual([items[0]]);
    expect(filterResources(items, "", "COMPLETED")).toEqual([items[1]]);
  });

  it("calculează termenul fără dependență de ora locală", () => {
    expect(dueInDays("2026-09-25", new Date("2026-09-24T18:00:00"))).toBe(1);
    expect(dueInDays("2026-09-20", new Date("2026-09-24T08:00:00"))).toBe(-4);
  });

  it("traduce statusurile cunoscute", () => {
    expect(statusLabel("AT_RISK")).toBe("La risc");
  });
});
