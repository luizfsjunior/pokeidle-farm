"use client";

import Link from "next/link";
import { createContext, useContext, useEffect, useState } from "react";
import { commandSummary } from "@/components/CommandButtons";
import { Sprite } from "@/components/Sprite";
import { useCommand } from "@/lib/useCommand";
import type { Atlas } from "@/lib/sprites";

/** O que a gaveta mostra de uma hunt (montado no servidor, em hunts/page.tsx). */
export type HuntDetail = {
  slug: string;
  title: string;
  speciesId: number;
  level: number;
  area: string;
  stones: string;
  gemsPer1000: number | null;
  measured: { label: string; value: string }[]; // números medidos no período, se a conta passou por lá
  here: string[]; // nicks que estão nela agora
};

type Ctx = { open: (slug: string) => void };
const DrawerCtx = createContext<Ctx>({ open: () => {} });

const HOURS: [number, string][] = [[0.5, "30 min"], [1, "1 h"], [2, "2 h"], [4, "4 h"], [8, "8 h"], [24, "24 h"]];

/**
 * Clicar numa hunt abre uma gaveta com os números dela e o botão de trocar. A troca usa o comando
 * hunt.select, que trava a hunt pelo prazo (os plugins gems e rank respeitam; docs/design/painel-fase-3.md).
 */
export function HuntDrawerProvider({ hunts, accounts, defaultAccount, atlas, looktypes, children }: {
  hunts: Record<string, HuntDetail>;
  accounts: { id: string; nick: string; enabled: boolean }[];
  defaultAccount: string | null;
  atlas: Atlas | null;
  looktypes: Record<number, number>;
  children: React.ReactNode;
}) {
  const [slug, setSlug] = useState<string | null>(null);
  const [account, setAccount] = useState(defaultAccount ?? accounts.find((a) => a.enabled)?.id ?? "");
  const [hours, setHours] = useState(2);
  const { send, cmd, error, busy } = useCommand();
  const hunt = slug ? hunts[slug] : null;

  useEffect(() => {
    if (!slug) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSlug(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [slug]);

  return (
    <DrawerCtx.Provider value={{ open: setSlug }}>
      {children}
      {hunt && (
        <>
          <div className="drawer-backdrop" onClick={() => setSlug(null)} aria-hidden />
          <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Hunt ${hunt.title}`}>
            <div className="drawer-head">
              <div className="drawer-stage">
                <Sprite mon={{ id: hunt.speciesId, species_id: hunt.speciesId, name: hunt.title }} atlas={atlas}
                  looktypes={new Map(Object.entries(looktypes).map(([k, v]) => [Number(k), v]))} size={72} />
              </div>
              <div>
                <h2>{hunt.title}</h2>
                <div className="small muted">nível {hunt.level}{hunt.area && ` · ${hunt.area}`}</div>
                {hunt.here.length > 0 && <span className="badge ready" style={{ marginTop: ".35rem" }}>agora: {hunt.here.join(", ")}</span>}
              </div>
              <button type="button" className="drawer-close" onClick={() => setSlug(null)} aria-label="Fechar">×</button>
            </div>
            <div className="drawer-body">
              <div className="action-box">
                <strong>Trocar para esta hunt</strong>
                <div className="row">
                  <select value={account} onChange={(e) => setAccount(e.target.value)} aria-label="Conta">
                    {accounts.map((a) => <option key={a.id} value={a.id} disabled={!a.enabled}>{a.nick}{a.enabled ? "" : " (desligada)"}</option>)}
                  </select>
                  <select value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Por quanto tempo">
                    {HOURS.map(([h, l]) => <option key={h} value={h}>por {l}</option>)}
                  </select>
                </div>
                <button type="button" disabled={busy || !account} onClick={() => void send(account, "hunt.select", { slug: hunt.slug, hours })}>
                  Trocar agora
                </button>
                {(cmd || error) && (
                  <p className={`small ${error || cmd?.status === "failed" ? "error" : "muted"}`} role="status" style={{ margin: 0 }}>
                    {error ?? (cmd && commandSummary(cmd))}
                  </p>
                )}
                <p className="small muted" style={{ margin: 0 }}>
                  Durante o prazo, os plugins gems e rank não trocam de hunt. Para soltar antes, use o card Hunt na página da conta.
                </p>
              </div>

              <div className="facts">
                <div><span>Gemas por 1.000 abates</span><span>{hunt.gemsPer1000 == null ? "—" : hunt.gemsPer1000.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}</span></div>
                {hunt.measured.map((m) => <div key={m.label}><span>{m.label}</span><span>{m.value}</span></div>)}
              </div>
              {hunt.stones && (
                <div>
                  <h3 style={{ marginTop: 0 }}>Pedras que caem</h3>
                  <p className="small secondary" style={{ margin: 0 }}>{hunt.stones}</p>
                </div>
              )}
              <Link href={`/pokedex`} className="small">Ver a espécie na Pokédex</Link>
            </div>
          </aside>
        </>
      )}
    </DrawerCtx.Provider>
  );
}

/** O nome da hunt como botão que abre a gaveta. */
export function HuntOpen({ slug, children }: { slug: string; children: React.ReactNode }) {
  const { open } = useContext(DrawerCtx);
  return <button type="button" className="hunt-open" onClick={() => open(slug)}>{children}</button>;
}
