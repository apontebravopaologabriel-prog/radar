import { expect, test } from "vitest";
import { formatPublicationDate, isRecentArchive, trackingDay } from "../lib/tracking-dates";

test("includes today and the previous six Lima calendar days", () => {
  const today = trackingDay(Date.parse("2026-11-13T04:00:00Z"));
  expect(today).toBe("2026-11-12");
  expect(isRecentArchive("2026-11-06T05:00:00Z", today)).toBe(true);
  expect(isRecentArchive("2026-11-06 04:59:59", today)).toBe(false);
  expect(isRecentArchive("2026-11-13T05:00:00Z", today)).toBe(false);
  expect(isRecentArchive("invalid", today)).toBe(false);
});


test("preserves undated offers and formats publication days consistently in Lima", () => {
  expect(formatPublicationDate(null)).toBe("Sin fecha");
  expect(formatPublicationDate("2026-11-12T03:00:00Z")).toBe(formatPublicationDate("2026-11-11"));
  expect(formatPublicationDate("2026-11-12T03:00:00")).toBe(formatPublicationDate("2026-11-12"));
});
