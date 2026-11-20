import { ago } from "@/lib/format";
import type { Alert } from "@/lib/alerts";

/** Alertas da conta, os críticos primeiro. Sem alerta, não ocupa espaço. */
export function Alerts({ items, compact = false }: { items: Alert[] | undefined; compact?: boolean }) {
  if (!items?.length) return null;
  return (
    <ul className={`alerts ${compact ? "alerts-compact" : ""}`} role="status">
      {items.map((a) => (
        <li key={`${a.text}-${a.at}`} className={`alert alert-${a.level}`}>
          <span>{a.text}</span>
          {!compact && <span className="muted small">{ago(a.at)}</span>}
        </li>
      ))}
    </ul>
  );
}
