"use client";

import { CommandStatus } from "@/components/CommandStatus";
import type { Mon } from "@/lib/profile";
import { useCommand } from "@/lib/useCommand";

/**
 * Botões de um pokémon fora da montagem: tornar ativo (quem está na equipe) e Coleção/Depot (quem não
 * está). Pôr e tirar da equipe fica só no "Montar equipe", que vai ao Pokécenter (o jogo só aceita lá).
 */
export function MonActions({ accountId, mon, team, isActive, inCollection, training = false }: {
  accountId: string;
  mon: Mon;
  team: Mon[];
  isActive: boolean;
  inCollection?: boolean; // undefined: não sabe (sem a coleção completa), não mostra o botão
  training?: boolean; // treino ligado: ele escolhe o ativo e desfaz a troca à mão em ~20 s (20/11)
}) {
  const { send, cmd, error, busy } = useCommand();
  const inTeam = team.some((t) => t.id === mon.id);
  if (isActive && !cmd && !error) return null;
  return (
    <div className="mon-actions">
      {inTeam && !isActive && training && (
        <span className="small muted">O treino da equipe escolhe o ativo: desligue no Modo (aba Agora) para trocar à mão.</span>
      )}
      {inTeam && !isActive && !training && (
        <button type="button" className="small" disabled={busy}
          onClick={() => void send(accountId, "team.active", { pokemon_id: mon.id })}>
          Tornar ativo
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
