"use client";

import { useState } from "react";
import { CommandStatus } from "./CommandStatus";
import { dateTime } from "@/lib/format";
import { loadGameRules, RULES_VERSION } from "@/lib/pokemon";
import { usePanel } from "@/lib/query/hooks";
import { BALL_NAMES } from "@/lib/sprites";
import { useCommand } from "@/lib/useCommand";
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

export function CaptureForm({ accountId, speciesId, speciesName, hunts: allHunts, balls, level = null }: {
  level?: number | null; // nível do treinador: hunt acima dele fica trancada no jogo
  accountId: string;
  speciesId: number;
  speciesName: string;
  hunts: { slug: string; name: string | null; level: number }[];
  balls?: Record<string, number>;
}) {
  const { send, cmd, error, busy } = useCommand();
  // as bolas do jogo (game_catalog.catalogoBolas); a Beast não se compra, só sai do estoque
  const { data: rules } = usePanel(["game-rules", RULES_VERSION], loadGameRules, { staleTime: 30 * 60_000 });
  const shop = rules?.balls ?? [];
  const hunts = level == null ? allHunts : allHunts.filter((h) => h.level <= level);
  const [hunt, setHunt] = useState(hunts[0]?.slug ?? "");
  const [ball, setBall] = useState(0); // 0: a que vale a pena (o worker escolhe pelo ouro por abate)
  const [stop, setStop] = useState<Stop>("first");
  // o texto do campo fica livre enquanto você digita (dá para apagar tudo); o número é ajustado ao sair
  // do campo e ao enviar
  const [countText, setCountText] = useState("5");
  const [hoursText, setHoursText] = useState("2");
  const count = clamp(countText, 1, 10_000, 5, true);
  const hours = clamp(hoursText, 0.25, 72, 2, false);

  if (hunts.length === 0 && allHunts.length > 0) {
    const need = Math.min(...allHunts.map((h) => h.level));
    return <p className="small muted" style={{ margin: 0 }}>A hunt desta espécie pede nível {need}, e a conta está no {level}: o jogo tranca até lá.</p>;
  }
  if (hunts.length === 0) {
    return <p className="small muted" style={{ margin: 0 }}>Nenhuma hunt tem esta espécie como principal, então não dá para mirar nela.</p>;
  }
  const go = () => void send(accountId, "capture.start", {
    species_id: speciesId, species_name: speciesName, hunt_slug: hunt, ball_id: ball || null,
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
          <option value={0}>A que vale a pena</option>
          {shop.map((b) => (
            <option key={b.id} value={b.id}>{b.name} · {b.price != null ? `${b.price} de ouro` : "só do estoque"}{balls ? ` · ${balls[String(b.id)] ?? 0} na mochila` : ""}</option>
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
      <CommandStatus cmd={cmd} error={error} />
    </div>
  );
}

export type ActiveCapture = {
  species_id: number;
  species_name: string | null;
  hunt_slug: string;
  ball_id: number | null;
  count: number | null;
  until: string | null;
  started_at: string;
  captured: number;
};

/** A captura em andamento, com o progresso e o botão de parar. */
export function CaptureStatus({ accountId, active }: { accountId: string; active: ActiveCapture }) {
  const { send, cmd, error, busy } = useCommand();
  const ball = active.ball_id == null ? "a bola que vale a pena" : BALL_NAMES[String(active.ball_id)] ?? `bola ${active.ball_id}`;
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
      <CommandStatus cmd={cmd} error={error} />
    </div>
  );
}
