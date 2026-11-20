"use client";

import { useEffect, useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { dateTime, num } from "@/lib/format";
import type { Profile } from "@/lib/profile";
import { useCommand } from "@/lib/useCommand";

/** Os ovos do jogo (shared/chocadeira.mjs e ovo-shiny.mjs): id da chocadeira, item na mochila, horas. */
const EGGS = [
  { id: "p2", item: 70091, name: "P2", hours: 6 },
  { id: "p3", item: 70092, name: "P3", hours: 12 },
  { id: "p4", item: 70093, name: "P4", hours: 24 },
  { id: "shiny", item: 70094, name: "Shiny", hours: 48 },
] as const;

type Slot = { slot: number; ovo: string; inicio: number; fim: number };

function parse(raw: unknown): { total: number; ovos: Slot[] } {
  const o = raw && typeof raw === "object" ? (raw as { total?: unknown; ovos?: unknown }) : {};
  const total = Math.max(1, Math.floor(Number(o.total)) || 1);
  const ovos = (Array.isArray(o.ovos) ? o.ovos : [])
    .filter((x): x is Slot => !!x && typeof x === "object" && Number.isInteger((x as Slot).slot))
    .map((x) => ({ slot: Number(x.slot), ovo: String(x.ovo), inicio: Number(x.inicio), fim: Number(x.fim) }));
  return { total, ovos };
}

function left(ms: number): string {
  if (ms <= 0) return "chocando agora";
  const h = Math.floor(ms / 3600_000);
  const m = Math.ceil((ms % 3600_000) / 60_000);
  return h > 0 ? `${h} h ${m} min` : `${m} min`;
}

/**
 * Chocadeira (estado.chocadeira {total, ovos}): as vagas, quanto falta para cada ovo chocar e os botões de pôr
 * os ovos da mochila. Choca sozinho no fim do tempo; o pokémon vai para o Depot. Os ovos se compram na Loja.
 */
export function IncubatorCard({ accountId, profile }: { accountId: string; profile: Profile }) {
  const { send, cmd, error, busy } = useCommand();
  const { total, ovos } = parse((profile.extra as Record<string, unknown> | undefined)?.chocadeira);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);
  const owned = EGGS.map((e) => ({ ...e, qty: profile.items[String(e.item)] ?? 0 })).filter((e) => e.qty > 0);
  const free = Array.from({ length: total }, (_, i) => i).filter((s) => !ovos.some((o) => o.slot === s));

  return (
    <section className="card stack">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Chocadeira</h2>
        <span className="small muted">{ovos.length} de {total} {total === 1 ? "vaga ocupada" : "vagas ocupadas"}</span>
      </div>
      <ul className="incubator">
        {Array.from({ length: total }, (_, s) => {
          const egg = ovos.find((o) => o.slot === s);
          const def = EGGS.find((e) => e.id === egg?.ovo);
          const pct = egg && egg.fim > egg.inicio ? Math.min(1, (now - egg.inicio) / (egg.fim - egg.inicio)) : 0;
          return (
            <li key={s} className={egg ? "is-busy" : "is-free"}>
              <strong>Vaga {s + 1}</strong>
              {egg ? (
                <>
                  <span>Ovo {def?.name ?? egg.ovo} · falta {left(egg.fim - now)}</span>
                  <div className="progress"><span style={{ width: `${pct * 100}%` }} /></div>
                  <span className="small muted">choca em {dateTime(new Date(egg.fim).toISOString())}</span>
                </>
              ) : <span className="muted">livre</span>}
            </li>
          );
        })}
      </ul>
      {free.length > 0 && (
        owned.length === 0
          ? <p className="small muted" style={{ margin: 0 }}>Nenhum ovo na mochila: compre na Loja acima.</p>
          : (
            <div className="row">
              {owned.map((e) => (
                <button key={e.id} type="button" className="small" disabled={busy}
                  onClick={() => void send(accountId, "incubator.put", { egg: e.id, slot: free[0] })}>
                  Chocar ovo {e.name} na vaga {free[0] + 1} <span className="muted">({num(e.qty)} · {e.hours} h)</span>
                </button>
              ))}
            </div>
          )
      )}
      <CommandStatus cmd={cmd} error={error} />
    </section>
  );
}
