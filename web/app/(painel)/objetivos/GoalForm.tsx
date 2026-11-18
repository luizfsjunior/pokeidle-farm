"use client";

import { useActionState, useState } from "react";
import { IV_STATS, type Account, type MetricDef } from "@/lib/types";
import { huntLabel } from "@/lib/format";
import { createGoal } from "./actions";

/** Novo objetivo: o essencial à vista; prazo, hunt e os filtros finos do pokémon em "Mais opções". */
export function GoalForm({ accounts, metrics, hunts }: { accounts: Account[]; metrics: MetricDef[]; hunts: string[] }) {
  const [kind, setKind] = useState<"capture" | "metric">("capture");
  const [error, action, pending] = useActionState(createGoal, null);

  return (
    <form action={action} className="stack goal-form">
      <div className="segmented" role="radiogroup" aria-label="Tipo">
        <button type="button" role="radio" aria-checked={kind === "capture"} className={kind === "capture" ? "on" : undefined} onClick={() => setKind("capture")}>Capturar pokémon</button>
        <button type="button" role="radio" aria-checked={kind === "metric"} className={kind === "metric" ? "on" : undefined} onClick={() => setKind("metric")}>Somar uma métrica</button>
      </div>
      <input type="hidden" name="kind" value={kind} />

      <div className="form-grid">
        <label style={{ gridColumn: "1 / -1" }}>Nome<input name="name" required placeholder={kind === "capture" ? "Dratini shiny" : "100 mi de ouro"} /></label>
        {kind === "capture" ? (
          <label style={{ gridColumn: "1 / -1" }}>Espécies (separe por vírgula)<input name="species" placeholder="Dratini, Dragonair" /></label>
        ) : (
          <label>Métrica
            <select name="metric" required>
              {metrics.map((m) => <option key={m.key} value={m.key}>{m.label} ({m.unit})</option>)}
            </select>
          </label>
        )}
        <label>{kind === "capture" ? "Quantos" : "Meta"}<input name="target" inputMode="decimal" required defaultValue={kind === "capture" ? "1" : ""} /></label>
        {kind === "capture" && (
          <label>Shiny
            <select name="shiny" defaultValue="">
              <option value="">Tanto faz</option>
              <option value="true">Sim</option>
              <option value="false">Não</option>
            </select>
          </label>
        )}
        <label>Conta
          <select name="account_id" defaultValue="">
            <option value="">Todas</option>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.nick}</option>)}
          </select>
        </label>
      </div>

      <details className="more">
        <summary>Mais opções</summary>
        <div className="stack" style={{ marginTop: ".6rem" }}>
          <div className="form-grid">
            <label>Prazo<input name="deadline" type="datetime-local" /></label>
            <label>Hunt
              <select name="hunt_slug" defaultValue="">
                <option value="">Qualquer</option>
                {hunts.map((h) => <option key={h} value={h}>{huntLabel(h)}</option>)}
              </select>
            </label>
            {kind === "capture" && <>
              <label>Qualidade mínima<input name="min_quality" inputMode="decimal" placeholder="1,5" /></label>
              <label>Potência mínima<input name="min_potency" inputMode="decimal" placeholder="3" /></label>
              <label>Soma mínima de IV<input name="min_iv_sum" inputMode="numeric" placeholder="150" /></label>
            </>}
          </div>
          {kind === "capture" && (
            <div className="form-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(90px, 1fr))" }} aria-label="IV mínimo por atributo">
              {IV_STATS.map((s) => <label key={s}>IV {s.toUpperCase()}<input name={`iv_${s}`} inputMode="numeric" /></label>)}
            </div>
          )}
        </div>
      </details>

      {error && <p className="error" role="alert">{error}</p>}
      <div><button type="submit" disabled={pending}>{pending ? "Criando…" : "Criar objetivo"}</button></div>
    </form>
  );
}
