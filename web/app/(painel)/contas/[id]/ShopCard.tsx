"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { num } from "@/lib/format";
import { loadGameRules, RULES_VERSION } from "@/lib/pokemon";
import type { Profile } from "@/lib/profile";
import { usePanel } from "@/lib/query/hooks";
import { loadSpend, SHOP_ITEMS } from "@/lib/shop";
import { useCommand } from "@/lib/useCommand";

/**
 * Loja do NPC (refatoracao-2026-11-20, seção 5): comprar à mão e ver o que a reposição automática gastou nas
 * últimas 24 h. Em 20/11 os revives drenaram ~1,4 M de ouro numa hora e nada mostrava isso.
 */
export function ShopCard({ accountId, profile }: { accountId: string; profile: Profile }) {
  const { send, cmd, error, busy } = useCommand();
  const { data: rules } = usePanel(["game-rules", RULES_VERSION], loadGameRules, { staleTime: 30 * 60_000 });
  const spend = usePanel(["shop-spend-24h", accountId], (sb) => loadSpend(sb, accountId), { staleTime: 60_000 }).data;
  const balls = (rules?.balls ?? []).filter((b) => b.price != null)
    .map((b) => ({ key: `ball:${b.id}`, kind: "ball" as const, id: b.id, name: b.name, price: b.price!, note: `captura ×${b.catchRate}` }));
  const items = SHOP_ITEMS.map((i) => ({ key: `item:${i.id}`, kind: "item" as const, ...i }));
  const all = [...balls, ...items];
  const [key, setKey] = useState("item:205");
  const [qtyText, setQtyText] = useState("10");
  const chosen = all.find((x) => x.key === key) ?? all[0];
  const qty = Math.max(1, Math.min(10_000, Math.round(Number(qtyText)) || 1));
  const cost = chosen ? chosen.price * qty : 0;
  const gold = profile.gold ?? 0;
  const have = (k: string, id: number) => (k.startsWith("ball") ? profile.balls[String(id)] : profile.items[String(id)]) ?? 0;
  const spent = [...(spend ?? new Map()).entries()].map(([k, v]) => ({ k, ...v, name: all.find((x) => x.key === k)?.name ?? k }))
    .sort((a, b) => b.gold - a.gold);
  const spentTotal = spent.reduce((s, x) => s + x.gold, 0);

  return (
    <section className="card stack">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Loja</h2>
        <span className="small muted">ouro: <strong className="num">{num(gold, { compact: true })}</strong></span>
      </div>
      {chosen && (
        <div className="row shop-form">
          <label>Item
            <select value={chosen.key} onChange={(e) => setKey(e.target.value)}>
              <optgroup label="Bolas">
                {balls.map((b) => <option key={b.key} value={b.key}>{b.name} · {num(b.price)} · tem {num(have(b.key, b.id))}</option>)}
              </optgroup>
              <optgroup label="Poções e revives">
                {items.map((i) => <option key={i.key} value={i.key}>{i.name} · {num(i.price)} · tem {num(have(i.key, i.id))}</option>)}
              </optgroup>
            </select>
          </label>
          <label>Quantidade
            <input type="number" inputMode="numeric" min={1} max={10000} value={qtyText} style={{ width: "6rem" }}
              onChange={(e) => setQtyText(e.target.value)} onBlur={() => setQtyText(String(qty))} />
          </label>
          <button type="button" disabled={busy || cost > gold}
            onClick={() => void send(accountId, "shop.buy", { kind: chosen.kind, id: chosen.id, qty })}>
            Comprar por {num(cost)}
          </button>
          <span className="small muted">{chosen.note}{cost > gold ? " · ouro insuficiente" : ""}</span>
        </div>
      )}
      <CommandStatus cmd={cmd} error={error} />
      <div>
        <h3 className="small" style={{ margin: ".4rem 0" }}>
          Gasto automático nas últimas 24 h: <span className={spentTotal > 500_000 ? "warn-text" : ""}>{num(spentTotal)} de ouro</span>
        </h3>
        {spent.length === 0 ? <p className="small muted" style={{ margin: 0 }}>Nenhuma compra automática.</p> : (
          <ul className="spend-list small">
            {spent.map((s) => <li key={s.k}><span>{s.name}</span><span className="num muted">{num(s.qty)} un.</span><span className="num">{num(s.gold)}</span></li>)}
          </ul>
        )}
      </div>
    </section>
  );
}
