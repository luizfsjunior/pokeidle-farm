"use client";

import { CommandStatus } from "./CommandStatus";
import { Sprite } from "./Sprite";
import type { Mon } from "@/lib/profile";
import type { Atlas } from "@/lib/sprites";
import { useCommand } from "@/lib/useCommand";

/**
 * A equipe do cartão de treinador. Com `switchFor` (página da conta), tocar num pokémon o torna o ativo
 * (`team.active`, na hunt mesmo, sem ir ao Pokécenter). Com o treino da equipe ligado, a troca fica
 * travada: ele escolhe o ativo e desfaria a troca em ~20 s.
 */
export function TeamStrip({ team, activeId, atlas, looktypes, switchFor }: {
  team: Mon[];
  activeId: number | null | undefined;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  switchFor?: { accountId: string; enabled: boolean; training: boolean };
}) {
  const { send, cmd, error, busy } = useCommand();
  const canSwitch = switchFor != null && switchFor.enabled && !switchFor.training;
  return (
    <>
      <ol className="team-strip" aria-label="Equipe">
        {team.map((m) => {
          const isActive = m.id === activeId;
          const name = m.name ?? `#${m.species_id ?? "?"}`;
          const body = (
            <>
              <Sprite mon={m} atlas={atlas} looktypes={looktypes} size={40} />
              <span className="num">{m.level ?? ""}</span>
            </>
          );
          return (
            <li key={m.id} title={`${name} nv ${m.level ?? "?"}${isActive ? " · ativo" : ""}`}
              className={isActive ? "is-active" : undefined}>
              {canSwitch && !isActive ? (
                <button type="button" className="team-pick" disabled={busy}
                  aria-label={`Tornar ${name} o ativo`}
                  onClick={() => void send(switchFor.accountId, "team.active", { pokemon_id: m.id })}>
                  {body}
                </button>
              ) : body}
            </li>
          );
        })}
      </ol>
      {switchFor?.training && team.length > 1 && (
        <p className="small muted team-hint">O treino da equipe escolhe o ativo: desligue no Modo para trocar à mão.</p>
      )}
      {canSwitch && !cmd && !error && team.length > 1 && (
        <p className="small muted team-hint">Toque num pokémon para torná-lo o ativo.</p>
      )}
      <CommandStatus cmd={cmd} error={error} inline />
    </>
  );
}
