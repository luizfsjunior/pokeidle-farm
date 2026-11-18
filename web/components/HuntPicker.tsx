"use client";

import { useMemo, useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { dateTime, num } from "@/lib/format";
import { useCommand } from "@/lib/useCommand";

export type HuntOption = { slug: string; name: string | null; level: number };
export type HuntHold = { slug: string; until: string } | null;

/** Por quanto tempo a hunt escolhida fica travada. */
export const HOLD_HOURS: [number, string][] = [[0.5, "30 min"], [1, "1 h"], [2, "2 h"], [4, "4 h"], [8, "8 h"], [24, "24 h"]];
const SHOWN = 8;

/**
 * Escolher a hunt pelo painel (comando hunt.select). A escolha fica travada pelo prazo: os plugins não trocam
 * até ele acabar (docs/design/painel-fase-3.md). Só lista as hunts até o nível do treinador (o jogo tranca o
 * resto); sem busca, mostra as mais altas, que são as que importam para XP.
 */
export function HuntPicker({ accountId, hunts, current, hold, trainerLevel, enabled }: {
  accountId: string;
  hunts: HuntOption[];
  current: string | null;
  hold: HuntHold;
  trainerLevel: number | null;
  enabled: boolean;
}) {
  const { send, cmd, error, busy } = useCommand();
  const [query, setQuery] = useState("");
  const [slug, setSlug] = useState<string | null>(null);
  const [hours, setHours] = useState(2);
  const name = (s: string | null) => hunts.find((h) => h.slug === s)?.name ?? s ?? "—";
  const holding = hold && new Date(hold.until) > new Date();

  const options = useMemo(() => {
    const q = query.trim().toLowerCase();
    return hunts
      .filter((h) => trainerLevel == null || h.level <= trainerLevel)
      .filter((h) => !q || `${h.name ?? ""} ${h.slug}`.toLowerCase().includes(q) || String(h.level) === q)
      .sort((a, b) => b.level - a.level)
      .slice(0, q ? 30 : SHOWN);
  }, [hunts, query, trainerLevel]);

  return (
    <div className="hunt-picker stack">
      {holding && (
        <p className="small" style={{ margin: 0 }}>
          Travada em <strong>{name(hold.slug)}</strong> até {dateTime(hold.until)}{" "}
          <button className="ghost small" disabled={busy} onClick={() => void send(accountId, "hunt.release")}>Soltar</button>
        </p>
      )}
      <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar hunt ou nível"
        aria-label="Buscar hunt" />
      <ul className="pick-list" role="listbox" aria-label="Hunts">
        {options.map((h) => (
          <li key={h.slug}>
            <button type="button" role="option" aria-selected={slug === h.slug} className={slug === h.slug ? "is-on" : undefined}
              onClick={() => setSlug(h.slug)}>
              <span>{h.name ?? h.slug}{h.slug === current && <span className="badge ready">agora</span>}</span>
              <span className="muted num">nv {num(h.level)}</span>
            </button>
          </li>
        ))}
        {options.length === 0 && <li className="muted small">Nenhuma hunt{trainerLevel != null ? ` até o nível ${num(trainerLevel)}` : ""}.</li>}
      </ul>
      <div className="row">
        <select value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Por quanto tempo">
          {HOLD_HOURS.map(([h, label]) => <option key={h} value={h}>por {label}</option>)}
        </select>
        <button className="small" disabled={busy || !slug || !enabled} onClick={() => slug && void send(accountId, "hunt.select", { slug, hours })}>
          {slug ? `Ir para ${name(slug)}` : "Escolha uma hunt"}
        </button>
      </div>
      <CommandStatus cmd={cmd} error={error} />
      {!enabled && <p className="small muted" style={{ margin: 0 }}>A conta está desligada.</p>}
    </div>
  );
}
