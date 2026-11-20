import { cancelCommand } from "@/app/(painel)/comandos/actions";
import { dateTime } from "@/lib/format";
import { PLUGIN_INFO } from "@/lib/plugins";
import { COMMAND_LABEL, COMMAND_STATUS_LABEL, type Command } from "@/lib/types";

const STATUS_BADGE: Record<string, string> = {
  pending: "connecting", running: "connecting", done: "ready", failed: "rejected", expired: "needs_login", cancelled: "",
};

function duration(c: Command): string {
  if (!c.started_at || !c.finished_at) return "—";
  const ms = new Date(c.finished_at).getTime() - new Date(c.started_at).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

const MODE: Record<string, string> = { xp: "XP", gold_xp_drop: "Ouro e drop", rank: "Rank", gems: "Gemas", capture: "Ouro e drop + bola em tudo" };
const fmtNum = (v: unknown) => (typeof v === "number" ? v.toLocaleString("pt-BR") : String(v ?? "?"));

/**
 * O que o comando pediu e o que aconteceu, em português (antes era o JSON do resultado). O JSON fica no title
 * da célula, para depurar.
 */
function detail(c: Command): string {
  if (c.error) return c.error;
  const p = (c.params ?? {}) as Record<string, unknown>;
  const r = (c.result ?? {}) as Record<string, unknown>;
  const applied = r.applied === "na próxima conexão" ? " (vale na próxima conexão)" : "";
  switch (c.type) {
    case "plugin.set": {
      const name = PLUGIN_INFO[String(p.plugin)]?.label ?? String(p.plugin);
      const state = p.enabled === false ? "desligado" : p.enabled === true ? "ligado" : "config salva";
      return `${name}: ${state}${applied}`;
    }
    case "focus.set": {
      const opts = [p.catch_all === true && "bola em tudo", (p.train as { enabled?: boolean } | undefined)?.enabled && "treinando a equipe"]
        .filter(Boolean).join(", ");
      return `Modo ${MODE[String(p.focus)] ?? String(p.focus)}${opts ? ` (${opts})` : ""}${applied}`;
    }
    case "hunt.select": return `${String(p.slug)} por ${fmtNum(p.hours ?? 2)} h${applied}`;
    case "capture.start": return `${String(p.species_name ?? `#${String(p.species_id)}`)}${p.count ? `, ${fmtNum(p.count)} capturas` : ""}${p.hours ? `, até ${fmtNum(p.hours)} h` : ""}`;
    case "team.active": return `pokémon ${String(p.pokemon_id)}`;
    case "team.apply": return Array.isArray(r.steps) ? (r.steps as string[]).join(", ") || "a equipe já estava assim" : "";
    case "collection.move": return `${r.moved != null ? `${fmtNum(r.moved)} pokémons` : `pokémon ${String(p.pokemon_id)}`} para ${p.to === "depot" ? "o Depot" : "a Coleção"}`;
    case "depot.sell": return r.sold != null ? `${fmtNum(r.sold)} vendidos${r.gold != null ? ` por ${fmtNum(r.gold)} de ouro` : ""}` : "";
    case "shop.buy": return `${fmtNum(p.qty)} × ${p.kind === "ball" ? "bola" : "item"} ${String(p.id)}${r.cost != null ? ` por ${fmtNum(r.cost)} de ouro` : ""}`;
    case "market.sell": return `${fmtNum(p.qty)} × item ${String(p.item_id)} a ${fmtNum(p.price)} ${p.currency === "gold" ? "de ouro" : "gemas"}`;
    case "market.cancel": return `anúncio ${String(p.listing_id)}`;
    case "incubator.put": return `ovo ${String(p.egg).toUpperCase()}${r.slot != null ? ` na vaga ${Number(r.slot) + 1}` : ""}`;
    case "ping": return r.state ? `sessão ${String(r.state)}${r.holder ? ` em ${String(r.holder)}` : ""}` : "";
    default: return "";
  }
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
            <td className="small secondary" style={{ maxWidth: 360, overflowWrap: "anywhere" }}
              title={JSON.stringify({ params: c.params, result: c.result })}>{detail(c)}</td>
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
