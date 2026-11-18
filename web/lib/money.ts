/**
 * Gemas e dólares num lugar só (docs/design/painel-ux-v2.md, seção 1). Antes a conta estava escrita de três
 * jeitos (um deles já sem a comissão) e cada tela tinha o seu preço.
 */

/** Comissão do Mercado em item vendido por gemas (fase-8-compensa.md; 13/10/7,5% são só de pokémon). */
export const ORB_FEE = 0.15;
/** Preço de recompra (saque) de uma gema, em US$. */
export const USD_PER_ORB = 0.009;
/** Pedras não são fonte de gemas: vendem a 2 com milhares na fila (game_items.category). */
export const STONE_CATEGORY = "stone";
/** Vendas mínimas para a mediana valer como referência (o mesmo `min_sales` do seller). */
export const MIN_SALES = 3;

/** Gemas brutas de uma venda → US$ no bolso (tira a comissão). */
export const gemsToUsd = (grossGems: number) => grossGems * (1 - ORB_FEE) * USD_PER_ORB;

/**
 * Preço de hoje de um item em gemas: a referência (mediana das vendas reais com `MIN_SALES`+ vendas, senão a
 * média de 7 dias do jogo), limitada pelo menor anúncio aberto, que é o preço pelo qual vende agora.
 */
export function gemPrice(p: { median?: number | null; sales?: number | null; avg?: number | null; minAsk?: number | null }): number | null {
  const ref = p.median != null && (p.sales ?? 0) >= MIN_SALES ? p.median : p.avg ?? null;
  if (ref == null) return p.minAsk ?? null;
  return p.minAsk != null ? Math.min(ref, p.minAsk) : ref;
}

const usdFmt = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const usd = (v: number | null | undefined) => (v == null ? "—" : `US$ ${usdFmt.format(v)}`);
