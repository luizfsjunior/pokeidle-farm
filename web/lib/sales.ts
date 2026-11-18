/**
 * Anúncios da conta no Mercado, montados a partir dos eventos (docs/design/pagina-vendas.md).
 *
 * Fontes, todas em `events`:
 * - `market.reply` aba `meus`: a lista dos próprios anúncios (`linhas`), pedida pelo seller a cada ciclo;
 * - `market.reply` aba `criado`: o anúncio recém-criado (`anuncio`);
 * - `action.sent` de `market.criar` e `market.cancelar` (o que o worker mandou);
 * - `unknown` com `t` = `venda` / `marketComprado`: avisos do jogo (formato ainda não mapeado).
 *
 * Um anúncio que some da lista `meus` sem ter sido cancelado pelo worker conta como vendido
 * (provável: também pode ter sido cancelado no navegador). Se a quantidade cai com o anúncio
 * aberto, a diferença conta como venda parcial.
 */

export type MarketEvent = {
  received_at: string;
  account_id: string;
  type: string;
  data: Record<string, unknown> | null;
  raw: Record<string, unknown> | null;
};

export type ListingStatus = "aberto" | "vendido" | "vendido?" | "cancelado" | "outro";

export type Listing = {
  id: string;
  accountId: string;
  itemId: number | null;
  name: string | null;
  qty: number; // quantidade atual (ou a última vista)
  firstQty: number;
  soldQty: number;
  price: number | null;
  currency: string;
  createdAt: string | null; // do jogo (criadoEm) ou o primeiro evento que mostrou o anúncio
  lastSeen: string;
  closedAt: string | null;
  status: ListingStatus;
  gameState: string | null; // `estado` como o jogo mandou, quando não é "aberto"
};

type Raw = Record<string, unknown>;

const str = (v: unknown) => (v == null ? null : String(v));
const numOr = (v: unknown, d: number) => (typeof v === "number" && Number.isFinite(v) ? v : d);
const msIso = (v: unknown) => (typeof v === "number" && v > 0 ? new Date(v).toISOString() : null);

function lines(raw: Raw | null): Raw[] {
  const l = raw?.linhas;
  return Array.isArray(l) ? (l.filter((x) => x && typeof x === "object") as Raw[]) : [];
}

function nameOf(a: Raw): string | null {
  const ficha = a.ficha as Raw | undefined;
  return str(ficha?.nome ?? a.nome ?? a.name);
}

/** Monta os anúncios a partir dos eventos (em qualquer ordem). */
export function buildListings(events: MarketEvent[]): Listing[] {
  const evs = [...events].sort((a, b) => a.received_at.localeCompare(b.received_at));
  const map = new Map<string, Listing>();
  const cancelled = new Map<string, string>(); // id -> quando o worker mandou cancelar
  const lastMine = new Map<string, { at: string; ids: Set<string> }>(); // por conta

  const upsert = (accountId: string, a: Raw, at: string) => {
    const id = str(a.id);
    if (!id) return null;
    const qty = numOr(a.qtd, 0);
    let l = map.get(id);
    if (!l) {
      l = {
        id, accountId, itemId: typeof a.itemId === "number" ? a.itemId : null, name: nameOf(a),
        qty, firstQty: qty, soldQty: 0, price: typeof a.preco === "number" ? a.preco : null,
        currency: str(a.moeda) ?? "orb", createdAt: msIso(a.criadoEm) ?? at, lastSeen: at,
        closedAt: null, status: "aberto", gameState: null,
      };
      map.set(id, l);
    } else {
      if (qty < l.qty) l.soldQty += l.qty - qty;
      l.qty = qty;
      l.lastSeen = at;
      l.name ??= nameOf(a);
      if (typeof a.preco === "number") l.price = a.preco;
    }
    const st = str(a.estado);
    if (st && st !== "aberto") {
      l.gameState = st;
      const wasOpen = l.closedAt == null;
      l.status = /vend|comprad/i.test(st) ? "vendido" : /cancel/i.test(st) ? "cancelado" : "outro";
      l.closedAt ??= at;
      if (wasOpen && l.status === "vendido") l.soldQty += l.qty; // o jogo pode manter a qtd vendida na linha
    }
    return l;
  };

  for (const e of evs) {
    const d = e.data ?? {};
    if (e.type === "market.reply" && d.aba === "criado") {
      const a = (e.raw?.anuncio ?? null) as Raw | null;
      if (a) upsert(e.account_id, a, e.received_at);
    } else if (e.type === "market.reply" && d.aba === "meus") {
      const ids = new Set<string>();
      for (const a of lines(e.raw)) {
        const l = upsert(e.account_id, a, e.received_at);
        if (l && l.status === "aberto") ids.add(l.id);
      }
      // abertos na lista anterior que sumiram nesta
      const prev = lastMine.get(e.account_id);
      if (prev) {
        for (const id of prev.ids) {
          const l = map.get(id);
          if (!l || ids.has(id) || l.status !== "aberto") continue;
          l.closedAt = e.received_at;
          if (cancelled.has(id)) l.status = "cancelado";
          else {
            l.status = "vendido?";
            l.soldQty += l.qty;
          }
        }
      }
      lastMine.set(e.account_id, { at: e.received_at, ids });
    } else if (e.type === "action.sent" && d.action === "market.cancelar") {
      const id = str((d.input as Raw | undefined)?.id);
      if (id) cancelled.set(id, e.received_at);
    }
  }
  // cancelado pelo worker, mas ainda sem lista `meus` depois: marca pelo pedido
  for (const [id, at] of cancelled) {
    const l = map.get(id);
    if (l && l.status === "aberto" && at > l.lastSeen) {
      l.status = "cancelado";
      l.closedAt = at;
    }
  }
  return [...map.values()].sort((a, b) => (b.closedAt ?? b.lastSeen).localeCompare(a.closedAt ?? a.lastSeen));
}

export const STATUS_LABEL: Record<ListingStatus, string> = {
  aberto: "Aberto",
  vendido: "Vendido",
  "vendido?": "Saiu da lista",
  cancelado: "Cancelado",
  outro: "Outro",
};

/** Resumo de um aviso do jogo cujo formato ainda não mapeamos: os campos simples, curtos. */
export function noticeSummary(raw: Raw | null): string {
  if (!raw) return "";
  return Object.entries(raw)
    .filter(([k, v]) => k !== "t" && v != null && typeof v !== "object")
    .slice(0, 8)
    .map(([k, v]) => `${k}: ${String(v).slice(0, 40)}`)
    .join(", ");
}
