"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { CaptureForm } from "@/components/Capture";
import { CommandStatus } from "@/components/CommandStatus";
import { HOLD_HOURS } from "@/components/HuntPicker";
import { Sprite } from "@/components/Sprite";
import { num } from "@/lib/format";
import { useCommand } from "@/lib/useCommand";
import type { Atlas } from "@/lib/sprites";

/** O que a gaveta mostra de uma hunt (montado em hunts/data.ts). */
export type HuntDetail = {
  slug: string;
  title: string;
  speciesId: number;
  level: number;
  area: string;
  measured: { label: string; value: string }[]; // números medidos no período, se a conta passou por lá
  here: string[]; // nicks que estão nela agora
};

type Ctx = { open: (slug: string) => void };
const DrawerCtx = createContext<Ctx>({ open: () => {} });

/**
 * Clicar numa hunt abre uma gaveta com os números dela e o botão de trocar. A troca usa o comando
 * hunt.select, que trava a hunt pelo prazo (os plugins gems e rank respeitam; docs/design/painel-fase-3.md).
 */
export function HuntDrawerProvider({ hunts, accounts, defaultAccount, atlas, looktypes, children }: {
  hunts: Record<string, HuntDetail>;
  accounts: { id: string; nick: string; enabled: boolean; level: number | null }[];
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
  const acc = accounts.find((a) => a.id === account);
  // o jogo tranca a área acima do nível do treinador
  const locked = hunt && acc?.level != null && hunt.level > acc.level ? hunt.level - acc.level : 0;

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
                <strong>Hunt manual</strong>
                <div className="row">
                  <select value={account} onChange={(e) => setAccount(e.target.value)} aria-label="Conta">
                    {accounts.map((a) => <option key={a.id} value={a.id} disabled={!a.enabled}>{a.nick}{a.enabled ? "" : " (desligada)"}</option>)}
                  </select>
                  <select value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Por quanto tempo">
                    {HOLD_HOURS.map(([h, l]) => <option key={h} value={h}>por {l}</option>)}
                  </select>
                </div>
                {locked > 0 ? (
                  <p className="small warn-text" style={{ margin: 0 }}>Trancada para {acc?.nick}: faltam {num(locked)} níveis de treinador.</p>
                ) : (
                  <button type="button" disabled={busy || !account} onClick={() => void send(account, "hunt.select", { slug: hunt.slug, hours })}>
                    Trocar agora
                  </button>
                )}
                <CommandStatus cmd={cmd} error={error} />
                <p className="small muted" style={{ margin: 0 }}>Um desvio: o modo não troca de hunt durante o prazo e volta depois. Encerra uma captura em andamento.</p>
              </div>

              {account && (
                <CaptureForm key={`${hunt.slug}-${account}`} accountId={account} speciesId={hunt.speciesId} speciesName={hunt.title}
                  hunts={[{ slug: hunt.slug, name: hunt.title, level: hunt.level }]} level={acc?.level ?? null} />
              )}

              {hunt.measured.length > 0 && (
                <div className="facts">
                  {hunt.measured.map((m) => <div key={m.label}><span>{m.label}</span><span>{m.value}</span></div>)}
                </div>
              )}
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
