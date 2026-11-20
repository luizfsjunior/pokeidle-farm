"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { ago, num } from "@/lib/format";
import type { Profile } from "@/lib/profile";
import { usePanel } from "@/lib/query/hooks";
import { loadAsks } from "@/lib/shop";
import { useCommand } from "@/lib/useCommand";
import { loadSales } from "../../economia/sales";
import type { ItemInfo } from "./ProfileSections";

/**
 * Mercado da conta (refatoracao-2026-11-20, seção 5): os anúncios abertos, cancelar, e anunciar à mão com o
 * menor anúncio e a fila do item ao lado. Antes o Mercado só aparecia como relatório do seller na Economia.
 */
export function MarketCard({ accountId, profile, items, sellerActive }: {
  accountId: string;
  profile: Profile;
  items: Map<string, ItemInfo>;
  sellerActive: boolean;
}) {
  const sales = usePanel(["vendas", accountId], (sb) => loadSales(sb, accountId), { staleTime: 60_000 });
  const open = (sales.data?.rows ?? []).filter((r) => r.status === "aberto");
  const bag = Object.entries(profile.items).filter(([, q]) => q > 0)
    .map(([id, qty]) => ({ id: Number(id), qty, name: items.get(id)?.name ?? `Item #${id}` }))
    .sort((a, b) => a.name.localeCompare(b.name));
  const asks = usePanel(["asks", bag.map((b) => b.id).join(",")], (sb) => loadAsks(sb, bag.map((b) => b.id)),
    { enabled: bag.length > 0, staleTime: 10 * 60_000 }).data;

  return (
    <section className="card stack">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Mercado</h2>
        <span className="small muted">gemas: <strong className="num">{num(profile.gems ?? 0)}</strong></span>
      </div>
      {sellerActive && (
        <p className="small warn-text" style={{ margin: 0 }}>
          O plugin de venda está ligado: ele também anuncia e cancela anúncios de pedras sozinho.
        </p>
      )}
      <h3 className="small" style={{ margin: 0 }}>Anúncios abertos ({open.length})</h3>
      {sales.isLoading ? <p className="small muted">Carregando…</p> : open.length === 0 ? (
        <p className="small muted" style={{ margin: 0 }}>Nenhum anúncio aberto.</p>
      ) : (
        <ul className="listing-list">
          {open.map((l) => <OpenListing key={l.id} accountId={accountId} id={l.id} label={l.label} qty={l.qty} price={l.price}
            currency={l.currency} since={l.createdAt} />)}
        </ul>
      )}
      <SellForm accountId={accountId} bag={bag} asks={asks} />
    </section>
  );
}

function OpenListing({ accountId, id, label, qty, price, currency, since }: {
  accountId: string; id: string; label: string; qty: number; price: number | null; currency: string; since: string | null;
}) {
  const { send, cmd, error, busy } = useCommand();
  const done = cmd?.status === "done";
  return (
    <li>
      <span>{label}</span>
      <span className="num small">{num(qty)} × {price == null ? "?" : num(price)} {currency === "orb" ? "gemas" : "ouro"}</span>
      <span className="small muted">{since ? ago(since) : ""}</span>
      <button type="button" className="ghost small" disabled={busy || done}
        onClick={() => void send(accountId, "market.cancel", { listing_id: /^\d+$/.test(id) ? Number(id) : id })}>
        {done ? "Cancelado" : "Cancelar"}
      </button>
      <CommandStatus cmd={cmd} error={error} inline />
    </li>
  );
}

function SellForm({ accountId, bag, asks }: {
  accountId: string;
  bag: { id: number; qty: number; name: string }[];
  asks: Map<number, { min: number | null; units: number }> | undefined;
}) {
  const { send, cmd, error, busy } = useCommand();
  const [itemId, setItemId] = useState<number | null>(null);
  const [qtyText, setQtyText] = useState("1");
  const [priceText, setPriceText] = useState("");
  const item = bag.find((b) => b.id === itemId) ?? null;
  const ask = item ? asks?.get(item.id) : undefined;
  const qty = item ? Math.max(1, Math.min(item.qty, Math.round(Number(qtyText)) || 1)) : 0;
  const price = Math.round(Number(priceText));
  const ok = item != null && Number.isFinite(price) && price >= 1;
  if (bag.length === 0) return null;
  return (
    <div className="stack sell-form">
      <h3 className="small" style={{ margin: 0 }}>Anunciar</h3>
      <div className="row">
        <label>Item
          <select value={itemId ?? ""} onChange={(e) => { setItemId(Number(e.target.value) || null); setQtyText("1"); setPriceText(""); }}>
            <option value="">Escolha um item da mochila</option>
            {bag.map((b) => <option key={b.id} value={b.id}>{b.name} · tem {num(b.qty)}</option>)}
          </select>
        </label>
        <label>Quantidade
          <input type="number" inputMode="numeric" min={1} max={item?.qty ?? 1} value={qtyText} style={{ width: "6rem" }} disabled={!item}
            onChange={(e) => setQtyText(e.target.value)} onBlur={() => setQtyText(String(qty || 1))} />
        </label>
        <label>Preço (gemas por unidade)
          <input type="number" inputMode="numeric" min={1} value={priceText} style={{ width: "7rem" }} disabled={!item}
            onChange={(e) => setPriceText(e.target.value)} placeholder={ask?.min != null ? String(Math.max(1, ask.min - 1)) : ""} />
        </label>
        <button type="button" disabled={busy || !ok}
          onClick={() => item && void send(accountId, "market.sell", { item_id: item.id, qty, price, currency: "orb" })}>
          Anunciar
        </button>
      </div>
      {item && (
        <p className="small muted" style={{ margin: 0 }}>
          {ask == null ? "Sem leitura recente do Mercado para este item."
            : ask.min == null ? "Ninguém mais anuncia este item agora."
            : <>Menor anúncio: <strong>{num(ask.min)} gemas</strong> · {num(ask.units)} unidades na fila.</>}
          {" "}O Mercado cobra 15% de comissão e segura o item por 2 min antes de vender.
        </p>
      )}
      <CommandStatus cmd={cmd} error={error} />
    </div>
  );
}
