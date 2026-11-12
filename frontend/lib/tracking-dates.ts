const DAY_MS = 86_400_000;
const limaDay = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Lima", year: "numeric", month: "2-digit", day: "2-digit" });

export function trackingDay(now = Date.now()) {
  return limaDay.format(now);
}

function recordedTimestamp(value: string) {
  const iso = value.replace(" ", "T");
  return Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

export function daysFromTrackingDay(value: string | null, today: string) {
  if (!value) return null;
  const timestamp = recordedTimestamp(value);
  if (!Number.isFinite(timestamp)) return null;
  return (Date.parse(today) - Date.parse(trackingDay(timestamp))) / DAY_MS;
}

export function isRecentArchive(value: string, today: string) {
  const age = daysFromTrackingDay(value, today);
  return age !== null && age >= 0 && age < 7;
}


const offerDate = new Intl.DateTimeFormat("es-PE", { timeZone: "America/Lima", day: "numeric", month: "short", year: "numeric" });

const shortOfferDate = new Intl.DateTimeFormat("es-PE", { timeZone: "America/Lima", day: "2-digit", month: "short" });

export function formatPublicationDate(value: string | null | undefined, compact = false) {
  if (!value) return compact ? "—" : "Sin fecha";
  const iso = value.replace(" ", "T");
  // A publication without a time zone already represents the source calendar day.
  const timestamp = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso.slice(0, 10)}T12:00:00-05:00`);
  if (!Number.isFinite(timestamp)) return compact ? "—" : "Sin fecha";
  if (!compact) return offerDate.format(timestamp);
  return shortOfferDate.formatToParts(timestamp).filter((part) => part.type !== "literal")
    .map((part) => part.value.replace(/\.$/, "").toUpperCase()).join(" ");
}
