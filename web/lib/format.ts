export const TZ = "America/Sao_Paulo";

const compact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const plain = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

export function num(v: number | null | undefined, opts: { compact?: boolean } = {}): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return opts.compact && Math.abs(n) >= 10_000 ? compact.format(n) : plain.format(n);
}

/** Horas com uma casa decimal (1,5). */
export const hours1 = (h: number) => plain.format(h);

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
  const d = new Date(iso);
  // o banco pode mandar ano de 5 dígitos (previsão de objetivo com ritmo ~0): o JS não lê e a página caía
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", { timeZone: TZ, dateStyle: "short", timeStyle: "short" }).format(d);
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

/** Selo curto de uma conta: o número do fim do nick (luizfsjunior_2 → 2), senão a inicial. */
export function nickBadge(nick: string): string {
  const m = nick.match(/_(\d+)$/);
  return m ? m[1] : nick.slice(0, 1).toUpperCase();
}

/** Nome legível de uma hunt a partir do slug (ancient_pupitar → Ancient Pupitar), onde só o slug está à mão. */
export const huntLabel = (slug: string) => slug.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
