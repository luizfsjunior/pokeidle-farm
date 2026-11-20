"use client";

import { CommandStatus } from "./CommandStatus";
import { useCommand } from "@/lib/useCommand";
import type { Account, CommandType } from "@/lib/types";

/**
 * Comandos da sessão no menu "⋯" do cabeçalho da conta (Curar, Reconectar, Ping, Ligar/Desligar). Ficavam
 * soltos no topo, com "Desligar" ao lado de "Curar" (refatoracao-2026-11-20, 4.1).
 */
export function CommandButtons({ account }: { account: Account }) {
  const { send, cmd, error, busy } = useCommand();
  const go = (type: CommandType) => () => {
    if (type === "account.disable" && !confirm(`Desligar ${account.nick}? A sessão é fechada.`)) return;
    void send(account.id, type);
  };
  return (
    <div className="cmd-buttons">
      <details className="more-menu">
        <summary aria-label="Mais ações da conta">⋯</summary>
        <div className="more-menu-list" role="menu">
          <button role="menuitem" className="ghost small" disabled={busy || !account.enabled} onClick={go("center.heal")}
            title="Cura a equipe no Pokécenter; com a equipe de pé, o jogo volta para a hunt">Curar a equipe</button>
          <button role="menuitem" className="ghost small" disabled={busy || !account.enabled} onClick={go("session.reconnect")}>Reconectar</button>
          <button role="menuitem" className="ghost small" disabled={busy} onClick={go("ping")}>Ping</button>
          <hr />
          {account.enabled
            ? <button role="menuitem" className="ghost small danger-text" disabled={busy} onClick={go("account.disable")}>Desligar a conta</button>
            : <button role="menuitem" className="small" disabled={busy} onClick={go("account.enable")}>Ligar a conta</button>}
        </div>
      </details>
      <CommandStatus cmd={cmd} error={error} inline />
    </div>
  );
}
