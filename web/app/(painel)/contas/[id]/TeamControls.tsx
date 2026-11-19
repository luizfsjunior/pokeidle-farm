"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { Hint } from "@/components/Page";
import type { Mon } from "@/lib/profile";
import { useCommand } from "@/lib/useCommand";

const TEAM_SLOTS = 5;

/** Botões de um pokémon na aba Equipe: tornar ativo, tirar ou pôr na equipe (team.active, team.move). */
export function MonActions({ accountId, mon, team, isActive, inCollection }: {
  accountId: string;
  mon: Mon;
  team: Mon[];
  isActive: boolean;
  inCollection?: boolean; // undefined: não sabe (sem a coleção completa), não mostra o botão
}) {
  const { send, cmd, error, busy } = useCommand();
  const inTeam = team.some((t) => t.id === mon.id);
  const used = new Set(team.map((t) => t.slot).filter((s): s is number => typeof s === "number"));
  const free = Array.from({ length: TEAM_SLOTS }, (_, i) => i).find((i) => !used.has(i));
  return (
    <div className="mon-actions">
      {inTeam ? (
        <>
          {!isActive && (
            <button type="button" className="small" disabled={busy}
              onClick={() => void send(accountId, "team.active", { pokemon_id: mon.id })}>
              Tornar ativo
            </button>
          )}
          {!isActive && (
            <button type="button" className="ghost small" disabled={busy}
              onClick={() => void send(accountId, "team.move", { pokemon_id: mon.id, slot: null })}>
              Tirar
            </button>
          )}
        </>
      ) : (
        <button type="button" className="small" disabled={busy || free === undefined}
          title={free === undefined ? "A equipe está cheia: tire alguém antes" : undefined}
          onClick={() => void send(accountId, "team.move", { pokemon_id: mon.id, slot: free })}>
          Pôr na equipe
        </button>
      )}
      {!inTeam && inCollection !== undefined && (
        <button type="button" className="ghost small" disabled={busy}
          title={inCollection ? "Volta para o Depot e entra na próxima venda" : "Fica guardado: a venda do Depot não leva"}
          onClick={() => void send(accountId, "collection.move", { pokemon_id: mon.id, to: inCollection ? "depot" : "colecao" })}>
          {inCollection ? "Mandar para o Depot" : "Guardar na Coleção"}
        </button>
      )}
      <CommandStatus cmd={cmd} error={error} inline />
    </div>
  );
}

type PluginRow = { plugin: string; enabled: boolean; config: Record<string, unknown> };

/** Card "Treinar a equipe": liga o plugin team_train com o nível alvo (docs/design/team-train.md). */
export function TeamTrainCard({ accountId, plugins, team }: { accountId: string; plugins: PluginRow[]; team: Mon[] }) {
  const { send, cmd, error, busy } = useCommand();
  const row = plugins.find((p) => p.plugin === "team_train");
  const on = row?.enabled === true;
  const saved = typeof row?.config.target_level === "number" ? row.config.target_level : 300;
  const [targetText, setTargetText] = useState<string>(String(saved));
  // vazio ou inválido enquanto digita: vale o salvo; fora do campo, o texto volta ao número usado
  const parsed = Math.round(Number(targetText));
  const target = targetText.trim() && Number.isFinite(parsed) ? Math.min(100_000, Math.max(2, parsed)) : saved;
  const done = team.filter((m) => (m.level ?? 0) >= saved).length;

  function apply(enabled: boolean) {
    void send(accountId, "plugin.set", { plugin: "team_train", enabled, config: { ...(row?.config ?? {}), target_level: target } });
  }

  return (
    <section className="card stack">
      <div className="spread">
        <div className="with-hint"><h2 style={{ margin: 0 }}>Treinar a equipe</h2><Hint>
          Só o pokémon ativo ganha XP cheio. Ligado, o worker troca o ativo para o membro da equipe mais fraco
          sempre que o atual chega no nível alvo, e o foco XP escolhe a hunt boa para ele. Com todos no alvo, volta
          para o mais forte. Os bosses pedem 5 pokémon no nível do boss (Kanto: 300).
        </Hint></div>
        <span className="muted small">{on ? `ligado · ${done} de ${team.length} no ${saved}` : "desligado"}</span>
      </div>
      <div className="row">
        <label className="row" style={{ gap: ".4rem" }}>
          Nível alvo
          <input type="number" inputMode="numeric" min={2} max={100000} value={targetText} style={{ width: "7rem" }}
            onChange={(e) => setTargetText(e.target.value)} onBlur={() => setTargetText(String(target))} />
        </label>
        <button type="button" disabled={busy || team.length === 0} onClick={() => apply(true)}>
          {on ? "Salvar" : "Ligar"}
        </button>
        {on && <button type="button" className="ghost" disabled={busy} onClick={() => apply(false)}>Desligar</button>}
      </div>
      {team.length < TEAM_SLOTS && (
        <p className="small muted" style={{ margin: 0 }}>A equipe tem {team.length} de {TEAM_SLOTS}: complete na aba Pokémons.</p>
      )}
      <CommandStatus cmd={cmd} error={error} />
    </section>
  );
}
