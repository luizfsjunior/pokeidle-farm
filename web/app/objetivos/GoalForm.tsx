"use client";

import { useActionState, useState } from "react";
import { IV_STATS, type Account, type MetricDef } from "@/lib/types";
import { createGoal } from "./actions";

export function GoalForm({ accounts, metrics, hunts }: { accounts: Account[]; metrics: MetricDef[]; hunts: string[] }) {
  const [kind, setKind] = useState<"capture" | "metric">("capture");
  const [error, action, pending] = useActionState(createGoal, null);

  return (
    <form action={action} className="card stack">
      <h2 style={{ margin: 0 }}>Novo objetivo</h2>
      <div className="row">
        <label className="row" style={{ display: "flex" }}>
          <input type="radio" name="kind" value="capture" checked={kind === "capture"} onChange={() => setKind("capture")} /> Capturar pokémon
        </label>
        <label className="row" style={{ display: "flex" }}>
          <input type="radio" name="kind" value="metric" checked={kind === "metric"} onChange={() => setKind("metric")} /> Somar uma métrica
        </label>
      </div>

      <div className="form-grid">
        <label style={{ gridColumn: "1 / -1" }}>Nome<input name="name" required placeholder={kind === "capture" ? "Dratini shiny 150+ IV" : "100M de gold"} /></label>
        {kind === "metric" && (
          <label>Métrica
            <select name="metric" required>
              {metrics.map((m) => <option key={m.key} value={m.key}>{m.label} ({m.unit})</option>)}
            </select>
          </label>
        )}
        <label>{kind === "capture" ? "Quantidade" : "Meta"}<input name="target" inputMode="decimal" required defaultValue={kind === "capture" ? "1" : ""} /></label>
        <label>Prazo (opcional)<input name="deadline" type="datetime-local" /></label>
        <label>Conta
          <select name="account_id" defaultValue="">
            <option value="">Todas as minhas</option>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.nick}</option>)}
          </select>
        </label>
        <label>Hunt
          <select name="hunt_slug" defaultValue="">
            <option value="">Qualquer</option>
            {hunts.map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
        </label>
      </div>

      {kind === "capture" && (
        <fieldset>
          <legend>Filtro do pokémon (deixe em branco o que não importa)</legend>
          <div className="form-grid">
            <label style={{ gridColumn: "1 / -1" }}>Espécies (separe por vírgula)<input name="species" placeholder="Dratini, Dragonair" /></label>
            <label>Qualidade mínima<input name="min_quality" inputMode="decimal" placeholder="1.5" /></label>
            <label>Potência mínima<input name="min_potency" inputMode="decimal" placeholder="3" /></label>
            <label>Shiny
              <select name="shiny" defaultValue="">
                <option value="">Tanto faz</option>
                <option value="true">Sim</option>
                <option value="false">Não</option>
              </select>
            </label>
            <label>Soma mínima de IV<input name="min_iv_sum" inputMode="numeric" placeholder="150" /></label>
          </div>
          <p className="muted small" style={{ marginBottom: ".4rem" }}>IV mínimo por atributo</p>
          <div className="form-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(90px, 1fr))" }}>
            {IV_STATS.map((s) => <label key={s}>{s.toUpperCase()}<input name={`iv_${s}`} inputMode="numeric" /></label>)}
          </div>
        </fieldset>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      <div><button type="submit" disabled={pending}>{pending ? "Criando…" : "Criar objetivo"}</button></div>
    </form>
  );
}
