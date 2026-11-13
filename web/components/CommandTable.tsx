import { cancelCommand } from "@/app/comandos/actions";
import { dateTime } from "@/lib/format";
import { COMMAND_LABEL, COMMAND_STATUS_LABEL, type Command } from "@/lib/types";

const STATUS_BADGE: Record<string, string> = {
  pending: "connecting", running: "connecting", done: "ready", failed: "rejected", expired: "needs_login", cancelled: "",
};

function duration(c: Command): string {
  if (!c.started_at || !c.finished_at) return "—";
  const ms = new Date(c.finished_at).getTime() - new Date(c.started_at).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function detail(c: Command): string {
  if (c.error) return c.error;
  const parts: string[] = [];
  if (c.type === "plugin.set" && c.params?.plugin) parts.push(String(c.params.plugin));
  if (c.result) parts.push(JSON.stringify(c.result));
  return parts.join(" · ");
}

export function CommandTable({ commands, nicks }: { commands: Command[]; nicks: Map<string, string> }) {
  if (commands.length === 0) return <p className="muted">Nenhum comando ainda.</p>;
  return (
    <table>
      <thead>
        <tr><th>Criado</th><th>Conta</th><th>Comando</th><th>Status</th><th className="r">Duração</th><th>Detalhe</th><th /></tr>
      </thead>
      <tbody>
        {commands.map((c) => (
          <tr key={c.id}>
            <td className="small">{dateTime(c.created_at)}</td>
            <td>{nicks.get(c.account_id) ?? "—"}</td>
            <td>{COMMAND_LABEL[c.type] ?? c.type}</td>
            <td><span className={`badge ${STATUS_BADGE[c.status] ?? ""}`}>{COMMAND_STATUS_LABEL[c.status] ?? c.status}</span></td>
            <td className="r small">{duration(c)}</td>
            <td className="small secondary" style={{ maxWidth: 360, overflowWrap: "anywhere" }}>{detail(c)}</td>
            <td>
              {c.status === "pending" && (
                <form action={cancelCommand}>
                  <input type="hidden" name="id" value={c.id} />
                  <button className="ghost small" type="submit">Cancelar</button>
                </form>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
