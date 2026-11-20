import { COMMAND_LABEL, COMMAND_STATUS_LABEL, type Command } from "@/lib/types";

/** Uma linha com o comando, a situação e o resultado (ou o erro). */
export function commandSummary(c: Command): string {
  const base = `${COMMAND_LABEL[c.type] ?? c.type}: ${COMMAND_STATUS_LABEL[c.status] ?? c.status}`;
  if (c.status === "failed" || c.status === "expired") return c.error ? `${base} — ${c.error}` : base;
  if (c.status !== "done" || !c.result) return base;
  const r = c.result as Record<string, unknown>;
  if (c.type === "ping") return `${base} — sessão ${String(r.state)}${r.holder ? ` em ${String(r.holder)}` : ""}`;
  if (c.type === "plugin.set" || c.type === "focus.set" || c.type === "hunt.release" || c.type === "capture.stop" || c.type === "capture.start") return `${base} — vale ${String(r.applied)}`;
  if (c.type === "hunt.select") return `${base} — ${String(r.slug)} até ${new Date(String(r.until)).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}, vale ${String(r.applied)}`;
  if (c.type === "shop.buy" && typeof r.cost === "number") return `${base} — ${r.cost.toLocaleString("pt-BR")} de ouro`;
  if (c.type === "collection.move" && typeof r.moved === "number") return `${base} — ${r.moved} marcados`;
  return base;
}

/** O que aconteceu com o último comando enviado (useCommand): na fila, feito, falhou e por quê. */
export function CommandStatus({ cmd, error, inline = false }: { cmd: Command | null; error: string | null; inline?: boolean }) {
  if (!cmd && !error) return null;
  const failed = !!error || cmd?.status === "failed" || cmd?.status === "expired";
  // na fila ou executando: pontinho pulsando; feito: verde com ✓; falhou: vermelho
  const state = failed ? "error" : cmd?.status === "done" ? "is-done" : cmd?.status === "cancelled" ? "muted" : "is-wait";
  const Tag = inline ? "span" : "p";
  return (
    <Tag className={`cmd-status small ${state}`} role="status">
      {state === "is-done" ? <span aria-hidden>✓</span> : <span className="cmd-dot" aria-hidden />}
      <span>{error ?? (cmd && commandSummary(cmd))}</span>
    </Tag>
  );
}
