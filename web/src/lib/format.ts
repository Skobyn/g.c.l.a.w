/**
 * Editorial / mission-control formatters.
 *
 * Timestamps read like datelines in a trade journal:
 *   15 · APR · 2026 · 14:30 UTC
 */

const MONTH_ABBR = [
  "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
];

const DAY_ABBR = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/**
 * ISO/Date → "15 · APR · 2026 · 14:30 UTC"
 * If `withTime` is false, returns "15 · APR · 2026".
 */
export function formatDatestamp(
  input: string | Date | null | undefined,
  opts: { withTime?: boolean; withDay?: boolean } = {},
): string {
  if (!input) return "—";
  const d = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(d.getTime())) return "—";

  const day = pad(d.getUTCDate());
  const mon = MONTH_ABBR[d.getUTCMonth()];
  const year = d.getUTCFullYear();
  const dayName = DAY_ABBR[d.getUTCDay()];
  const hh = pad(d.getUTCHours());
  const mm = pad(d.getUTCMinutes());

  const core = `${day} · ${mon} · ${year}`;
  const prefix = opts.withDay ? `${dayName} ${core}` : core;
  if (opts.withTime === false) return prefix;
  return `${prefix} · ${hh}:${mm} UTC`;
}

/** Compact clock for turn margins: "14:30:02" (UTC). */
export function formatTimestamp(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const d = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(d.getTime())) return "—";
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/** "16 APR · 04:12" — short, local, used on board cards. */
export function formatShortStamp(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const d = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(d.getTime())) return "—";
  const day = pad(d.getDate());
  const mon = MONTH_ABBR[d.getMonth()];
  const hh = pad(d.getHours());
  const mm = pad(d.getMinutes());
  return `${day} ${mon} · ${hh}:${mm}`;
}

/** "WED · 16 APR · 2026 · 04:12 UTC" — long-form ticker dateline. */
export function formatTickerStamp(input: Date = new Date()): string {
  const d = input;
  const dayName = DAY_ABBR[d.getUTCDay()];
  const day = pad(d.getUTCDate());
  const mon = MONTH_ABBR[d.getUTCMonth()];
  const year = d.getUTCFullYear();
  const hh = pad(d.getUTCHours());
  const mm = pad(d.getUTCMinutes());
  return `${dayName} · ${day} ${mon} · ${year} · ${hh}:${mm} UTC`;
}

/** "H" / "M" / "L" from a priority value. */
export function priorityGlyph(p: string | undefined | null): string {
  if (!p) return "·";
  const c = p[0]?.toUpperCase();
  if (c === "H" || c === "M" || c === "L") return c;
  return "·";
}

/** Zero-padded call number: 1 → "01", 14 → "14". */
export function callNumber(n: number): string {
  return n.toString().padStart(2, "0");
}
