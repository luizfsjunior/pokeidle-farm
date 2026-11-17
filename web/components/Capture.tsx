"use client";

import { useState } from "react";
import { commandSummary } from "./CommandButtons";
import { dateTime } from "@/lib/format";
import { useCommand } from "@/lib/useCommand";

export const BALLS: { id: number; name: string; price: number }[] = [
  { id: 1, name: "Poké Ball", price: 5 },
  { id: 2, name: "Great Ball", price: 20 },
  { id: 3, name: "Super Ball", price: 50 },
  { id: 4, name: "Ultra Ball", price: 130 },
];
type Stop = "count" | "time" | "first" | "manual";

/**
 * "Capturar esta espécie" (comando capture.start; docs/design/captura-alvo.md): o worker vai para a hunt
 * da espécie com a bola escolhida e para no que for escolhido (N capturas, tempo, o que vier primeiro, ou
 * só pelo botão Parar).
 */
/** Texto do campo → número dentro dos limites (vazio ou inválido volta ao padrão). */
function clamp(text: string, min: number, max: number, fallback: number, int: boolean): number {
  const n = Number(text.replace(",", "."));
  if (!text.trim() || !Number.isFinite(n)) return fallback;
  const v = Math.min(max, Math.max(min, n));
  return int ? Math.round(v) : v;
}

export function CaptureForm({ accountId, speciesId, speciesName, hunts, balls }: {
  accountId: string;
  speciesId: number;
  speciesName: string;
  hunts: { slug: string; name: string | null; level: number }[];
  balls?: Record<string, number>;
}) {
  const { send, cmd, error, busy } = useCommand();
  const [hunt, setHunt] = useState(hunts[0]?.slug ?? "");
  const [ball, setBall] = useState(4);
  const [stop, setStop] = useState<Stop>("first");
  // o texto do campo fica livre enquanto você digita (dá para apagar tudo); o número é ajustado ao sair
  // do campo e ao enviar
  const [countText, setCountText] = useState("5");
  const [hoursText, setHoursText] = useState("2");
  const count = clamp(countText, 1, 10_000, 5, true);
  const hours = clamp(hoursText, 0.25, 72, 2, false);

  if (hunts.length === 0) {
    return <p className="small muted" style={{ margin: 0 }}>Nenhuma hunt tem esta espécie como principal, então não dá para mirar nela.</p>;
  }
  const go = () => void send(accountId, "capture.start", {
    species_id: speciesId, species_name: speciesName, hunt_slug: hunt, ball_id: ball,
    count: stop === "count" || stop === "first" ? count : null,
    hours: stop === "time" || stop === "first" ? hours : null,
  });

  return (
    <div className="action-box">
      <strong>Capturar {speciesName}</strong>
      {hunts.length > 1 && (
        <label>Hunt
          <select value={hunt} onChange={(e) => setHunt(e.target.value)}>
            {hunts.map((h) => <option key={h.slug} value={h.slug}>nv {h.level} · {h.name ?? h.slug}</option>)}
          </select>
        </label>
      )}
      <label>Bola
        <select value={ball} onChange={(e) => setBall(Number(e.target.value))}>
          {BALLS.map((b) => (
            <option key={b.id} value={b.id}>{b.name} · {b.price} de ouro{balls ? ` · ${balls[String(b.id)] ?? 0} na mochila` : ""}</option>
          ))}
        </select>
      </label>
      <label>Parar
        <select value={stop} onChange={(e) => setStop(e.target.value as Stop)}>
          <option value="first">no que vier primeiro: capturas ou tempo</option>
          <option value="count">depois de N capturas</option>
          <option value="time">depois de um tempo</option>
          <option value="manual">só quando eu parar</option>
        </select>
      </label>
      {(stop === "count" || stop === "first" || stop === "time") && (
        <div className="row">
          {(stop === "count" || stop === "first") && (
            <label>Capturas<input type="number" inputMode="numeric" min={1} max={10000} value={countText}
              onChange={(e) => setCountText(e.target.value)} onBlur={() => setCountText(String(count))} /></label>
          )}
          {(stop === "time" || stop === "first") && (
            <label>Horas<input type="number" inputMode="decimal" min={0.25} max={72} step={0.25} value={hoursText}
              onChange={(e) => setHoursText(e.target.value)} onBlur={() => setHoursText(String(hours))} /></label>
          )}
        </div>
      )}
      <button type="button" disabled={busy || !hunt} onClick={go}>Começar a captura</button>
      {(cmd || error) && (
        <p className={`small ${error || cmd?.status === "failed" ? "error" : "muted"}`} role="status" style={{ margin: 0 }}>
          {error ?? (cmd && commandSummary(cmd))}
        </p>
      )}
    </div>
  );
}

export type ActiveCapture = {
  species_id: number;
  species_name: string | null;
  hunt_slug: string;
  ball_id: number;
  count: number | null;
  until: string | null;
  started_at: string;
  captured: number;
};

/** A captura em andamento, com o progresso e o botão de parar. */
export function CaptureStatus({ accountId, active }: { accountId: string; active: ActiveCapture }) {
  const { send, cmd, error, busy } = useCommand();
  const ball = BALLS.find((b) => b.id === active.ball_id)?.name ?? `bola ${active.ball_id}`;
  const pct = active.count ? Math.min(1, active.captured / active.count) : null;
  return (
    <div className="action-box">
      <div className="spread">
        <strong>Capturando {active.species_name ?? `#${active.species_id}`}</strong>
        <span className="badge ready">ativa</span>
      </div>
      <div className="small secondary">
        {active.captured}{active.count ? ` de ${active.count}` : ""} capturas · {ball} · desde {dateTime(active.started_at)}
        {active.until ? ` · até ${dateTime(active.until)}` : active.count ? "" : " · até você parar"}
      </div>
      {pct != null && <div className="progress"><span style={{ width: `${pct * 100}%` }} /></div>}
      <button type="button" className="ghost" disabled={busy} onClick={() => void send(accountId, "capture.stop")}>Parar a captura</button>
      {(cmd || error) && (
        <p className={`small ${error || cmd?.status === "failed" ? "error" : "muted"}`} role="status" style={{ margin: 0 }}>
          {error ?? (cmd && commandSummary(cmd))}
        </p>
      )}
    </div>
  );
}
