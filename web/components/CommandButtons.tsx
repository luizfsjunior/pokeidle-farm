"use client";

import { CommandStatus } from "./CommandStatus";
import { useCommand } from "@/lib/useCommand";
import type { Account, CommandType } from "@/lib/types";

/** Ping, Reconectar e Ligar/Desligar, no cabeçalho da página da conta. */
export function CommandButtons({ account }: { account: Account }) {
  const { send, cmd, error, busy } = useCommand();
  const go = (type: CommandType) => () => {
    if (type === "account.disable" && !confirm(`Desligar ${account.nick}? A sessão é fechada.`)) return;
    void send(account.id, type);
  };
  return (
    <div className="cmd-buttons">
      <div className="row">
        <button className="ghost small" disabled={busy} onClick={go("ping")}>Ping</button>
        <button className="ghost small" disabled={busy || !account.enabled} onClick={go("session.reconnect")}>Reconectar</button>
        {account.enabled
          ? <button className="ghost small" disabled={busy} onClick={go("account.disable")}>Desligar</button>
          : <button className="small" disabled={busy} onClick={go("account.enable")}>Ligar</button>}
      </div>
      <CommandStatus cmd={cmd} error={error} />
    </div>
  );
}
