"use client";

import Link from "next/link";
import { useCommand } from "@/lib/useCommand";
import { COMMAND_LABEL, COMMAND_STATUS_LABEL, type Account, type Command, type CommandType } from "@/lib/types";

export function commandSummary(c: Command): string {
  const base = `${COMMAND_LABEL[c.type] ?? c.type}: ${COMMAND_STATUS_LABEL[c.status] ?? c.status}`;
  if (c.status === "failed" || c.status === "expired") return c.error ? `${base} — ${c.error}` : base;
  if (c.status !== "done" || !c.result) return base;
  const r = c.result as Record<string, unknown>;
  if (c.type === "ping") return `${base} — sessão ${String(r.state)}${r.holder ? ` em ${String(r.holder)}` : ""}`;
  if (c.type === "plugin.set") return `${base} — vale ${String(r.applied)}`;
  return base;
}

export function CommandButtons({ account }: { account: Account }) {
  const { send, cmd, error, busy } = useCommand();
  const go = (type: CommandType) => () => {
    if (type === "account.disable" && !confirm(`Desligar ${account.nick}? A sessão é fechada.`)) return;
    void send(account.id, type);
  };
  return (
    <div style={{ marginTop: ".9rem" }}>
      <div className="row">
        <button className="ghost small" disabled={busy} onClick={go("ping")}>Ping</button>
        <button className="ghost small" disabled={busy || !account.enabled} onClick={go("session.reconnect")}>Reconectar</button>
        {account.enabled
          ? <button className="ghost small" disabled={busy} onClick={go("account.disable")}>Desligar</button>
          : <button className="small" disabled={busy} onClick={go("account.enable")}>Ligar</button>}
        <Link href={`/contas/${account.id}`} className="small">Plugins</Link>
      </div>
      {(cmd || error) && (
        <p className={`small ${error || cmd?.status === "failed" ? "error" : "muted"}`} role="status" style={{ margin: ".4rem 0 0" }}>
          {error ?? (cmd && commandSummary(cmd))}
          {cmd?.status === "pending" && " (o worker busca a cada 5 s)"}
        </p>
      )}
    </div>
  );
}
