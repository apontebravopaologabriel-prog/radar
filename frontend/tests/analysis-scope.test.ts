import { describe, expect, it } from "vitest";
import { analysisScope, filtersFromScope } from "../lib/analysis-scope";
import { scopeParams } from "../lib/analysis-api";
import { INITIAL_FILTERS } from "../lib/radar-format";

describe("shared analysis scope", () => {
  it("keeps all map filters, explicit zero pay and the choice to include other markets", () => {
    const filters = { ...INITIAL_FILTERS, source: "computrabajo", search: "datos", area: "Data / BI", seniority: "junior", work_mode: "hybrid", min_salary: "0", max_salary: "2500", relevance_tier: "", max_age_days: "30", profile_mode: "saved" };
    const scope = analysisScope(filters, "SQL");
    const params = scopeParams(scope);
    expect(params.get("min_salary")).toBe("0");
    expect(params.get("relevance_tier")).toBe("");
    expect(params.get("max_age_days")).toBe("30");
    expect(params.get("skill")).toBe("SQL");
    expect(filtersFromScope(scope)).toEqual(filters);
  });
  it("serializes geography and empty radar explicitly without making up a center", () => {
    const scope = analysisScope(INITIAL_FILTERS, null);
    expect(scopeParams({ ...scope, empty: true }).get("empty")).toBe("true");
    expect(scopeParams({ ...scope, latitude: 0, longitude: -77, radius_km: 5 }).get("latitude")).toBe("0");
    expect(scopeParams(scope).has("radius_km")).toBe(false);
    expect(scopeParams(scope).has("min_salary")).toBe(false);
  });
});
