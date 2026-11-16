"use client";

import { useMemo, useState } from "react";
import { commandSummary } from "@/components/CommandButtons";
import { dateTime } from "@/lib/format";
import { useCommand } from "@/lib/useCommand";

export type HuntOption = { slug: string; name: string | null; level: number };
export type HuntHold = { slug: string; until: string } | null;

const HOURS: [number, string][] = [[0.5, "30 min"], [1, "1 h"], [2, "2 h"], [4, "4 h"], [8, "8 h"], [24, "24 h"]];

/**
 * Escolher a hunt pelo painel (comando hunt.select). A escolha fica travada pelo prazo: os plugins
 * gems e rank não trocam até ele acabar (docs/design/painel-fase-3.md).
 */
export function HuntPicker({ accountId, hunts, current, hold, level, enabled }: {
  accountId: string;
  hunts: HuntOption[];
  current: string | null;
  hold: HuntHold;
  level: number | null;
  enabled: boolean;
}) {
  const { send, cmd, error, busy } = useCommand();
  const [slug, setSlug] = useState(hold?.slug ?? current ?? "");
  const [hours, setHours] = useState(2);
  const [onlyMine, setOnlyMine] = useState(level != null);
  const name = (s: string | null) => hunts.find((h) => h.slug === s)?.name ?? s ?? "—";
  const options = useMemo(
    () => hunts.filter((h) => !onlyMine || level == null || h.level <= level + 5 || h.slug === slug),
    [hunts, onlyMine, level, slug],
  );
  const holding = hold && new Date(hold.until) > new Date();

  return (
    <div className="hunt-picker">
      <p className="small" style={{ margin: 0 }}>
        Agora em <strong>{name(current)}</strong>
        {holding && <> · travada em <strong>{name(hold.slug)}</strong> até {dateTime(hold.until)}</>}
      </p>
      <div className="row">
        <select value={slug} onChange={(e) => setSlug(e.target.value)} aria-label="Hunt">
          <option value="" disabled>Escolha a hunt</option>
          {options.map((h) => (
            <option key={h.slug} value={h.slug}>nv {h.level} · {h.name ?? h.slug}</option>
          ))}
        </select>
        <select value={hours} onChange={(e) => setHours(Number(e.target.value))} aria-label="Por quanto tempo">
          {HOURS.map(([h, label]) => <option key={h} value={h}>por {label}</option>)}
        </select>
        <button className="small" disabled={busy || !slug || !enabled} onClick={() => void send(accountId, "hunt.select", { slug, hours })}>
          Ir para esta hunt
        </button>
        {holding && (
          <button className="ghost small" disabled={busy} onClick={() => void send(accountId, "hunt.release")}>
            Soltar a trava
          </button>
        )}
      </div>
      {level != null && (
        <label className="small muted">
          <input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} /> só hunts até o nível {level + 5}
        </label>
      )}
      {(cmd || error) && (
        <p className={`small ${error || cmd?.status === "failed" ? "error" : "muted"}`} role="status" style={{ margin: 0 }}>
          {error ?? (cmd && commandSummary(cmd))}
        </p>
      )}
      {!enabled && <p className="small muted" style={{ margin: 0 }}>A conta está desligada.</p>}
    </div>
  );
}
