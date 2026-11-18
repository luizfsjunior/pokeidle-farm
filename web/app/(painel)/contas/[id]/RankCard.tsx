import { Stat } from "@/components/Page";
import { ago, num } from "@/lib/format";
import { BALL_NAMES } from "@/lib/sprites";
import type { QueueItem, RankSummary } from "@/lib/rank";

const REASON: Record<string, string> = {
  start: "subida",
  week: "lista da semana",
  captured: "captura do alvo",
  captured_other: "captura de outra da fila",
  level_up: "subiu de nível",
  timeout: "tempo esgotado no alvo",
  week_rollover: "virada da semana",
  ball_changed: "troca de bola",
  switch_failed: "troca de hunt falhou",
  switch_cap: "teto de trocas por hora",
  sem_catalogo: "sem catálogo",
};

const minutes = (q: QueueItem | null) => (q ? `${num(q.hours * 60)} min` : "—");
const label = (q: QueueItem) => q.name ?? q.slug;

/** Card "Rank semanal" (docs/design/fase-3b-metricas-e-card.md, seção 2). */
export function RankCard({ rank }: { rank: RankSummary }) {
  const { plan, position, mode } = rank;
  const empty = !plan && rank.species === null;
  const names = new Map((plan?.queue ?? []).map((q) => [q.species_id, label(q)]));

  return (
    <section className="card stack">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Rank semanal</h2>
        <span className="muted small">semana de {rank.week.split("-").reverse().join("/")}</span>
      </div>
      {empty ? (
        <p className="muted" style={{ margin: 0 }}>Sem dados desta semana.</p>
      ) : (
        <>
          <div className="stats">
            <Stat label="Espécies na semana" value={num(rank.species)} />
            <Stat
              label="Posição"
              value={
                !position ? "—"
                  : position.inside ? `${num(position.position)}º`
                  : `fora do top 100 (faltam ${num(position.missing)})`
              }
            />
            <Stat label="Espécies por hora ativa" value={num(rank.ratePerHour)} />
            <Stat
              label="Modo"
              value={plan?.dryRun ? "ensaio" : mode?.mode === "fallback" ? "fallback (fila acabou)" : mode?.mode === "active" ? "ativo" : "—"}
            />
          </div>
          {plan && (
            <p className="small" style={{ margin: 0 }}>
              <strong>Agora:</strong> {plan.current ?? "—"} → alvo{" "}
              {plan.target ? `${label(plan.target)} (~${minutes(plan.target)})` : "nenhum"}
              {plan.ballId != null && ` · ${BALL_NAMES[String(plan.ballId)] ?? `bola ${plan.ballId}`}`}
              <span className="muted"> · {REASON[plan.reason] ?? plan.reason}, {ago(plan.at)}</span>
            </p>
          )}
          {plan && plan.queue.length > 0 && (
            <div className="small">
              <strong>Fila</strong> <span className="muted">({num(plan.queueLen)} hunts)</span>
              <ol style={{ margin: ".25rem 0 0", paddingLeft: "1.25rem" }}>
                {plan.queue.slice(0, 5).map((q) => (
                  <li key={q.slug}>{label(q)} <span className="muted">· {q.slug} · ~{minutes(q)}</span></li>
                ))}
              </ol>
            </div>
          )}
          {plan && plan.skipped.length > 0 && (
            <p className="small" style={{ margin: 0 }}>
              <strong>Puladas:</strong> {plan.skipped.map((id) => names.get(id) ?? `#${id}`).join(", ")}
            </p>
          )}
          {(rank.failures.length > 0 || (plan?.degraded.length ?? 0) > 0) && (
            <div className="small">
              <strong>Problemas</strong>
              <ul style={{ margin: ".25rem 0 0", paddingLeft: "1.25rem" }}>
                {plan?.degraded.map((d) => <li key={d} className="error">degradado: {d}</li>)}
                {rank.failures.map((f) => (
                  <li key={f.at}>troca para {f.slug ?? "—"} falhou ({f.reason ?? "?"}), {ago(f.at)}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
