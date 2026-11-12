export const TZ = "America/Sao_Paulo";

const compact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const plain = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

export function num(v: number | null | undefined, opts: { compact?: boolean } = {}): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return opts.compact && Math.abs(n) >= 10_000 ? compact.format(n) : plain.format(n);
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return "—";
  return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(Number(v) * 100)}%`;
}

/** Probabilidade pequena: 1 em N quando abaixo de 1%. */
export function chance(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (n > 0 && n < 0.01) return `1 em ${plain.format(Math.round(1 / n))}`;
  return pct(n);
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
}

export function hourLabel(iso: string, bucket: "hour" | "day"): string {
  const d = new Date(iso);
  return bucket === "hour"
    ? new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(d)
    : new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, day: "2-digit", month: "2-digit", weekday: "short" }).format(d);
}

/** Data de hoje (YYYY-MM-DD) no fuso de Brasília. */
export function todaySP(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

/** "há 5 min" a partir de um ISO. */
export function ago(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "agora";
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  return `há ${Math.round(s / 86400)} d`;
}
