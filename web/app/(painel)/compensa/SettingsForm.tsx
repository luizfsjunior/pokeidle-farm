"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export type EvalSettings = {
  machine_watts: number | null;
  marginal: boolean;
  kwh_price_brl: number | null;
  usd_brl: number | null;
  window_days: number;
};

const toNum = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

/** Parâmetros de custo do "Compensa?" (docs/design/fase-8-compensa.md, seção 2). */
export function SettingsForm({ initial }: { initial: EvalSettings }) {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const [watts, setWatts] = useState(initial.machine_watts?.toString() ?? "");
  const [kwh, setKwh] = useState(initial.kwh_price_brl?.toString() ?? "");
  const [usd, setUsd] = useState(initial.usd_brl?.toString() ?? "");
  const [marginal, setMarginal] = useState(initial.marginal);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const row = { machine_watts: toNum(watts), kwh_price_brl: toNum(kwh), usd_brl: toNum(usd), marginal };
    if (Object.values(row).some((v) => typeof v === "number" && (Number.isNaN(v) || v < 0))) {
      setMsg("use números positivos (ou deixe vazio)");
      return;
    }
    if (row.usd_brl === 0) { setMsg("o câmbio não pode ser 0"); return; }
    setBusy(true);
    const { error } = await supabase.from("evaluation_settings").upsert(row, { onConflict: "owner_id" });
    setBusy(false);
    setMsg(error ? error.message : "salvo");
    if (!error) router.refresh();
  }

  return (
    <form onSubmit={submit} className="card stack">
      <h2 style={{ margin: 0 }}>Custo de energia</h2>
      <label className="row">
        <input type="checkbox" checked={marginal} onChange={(e) => setMarginal(e.target.checked)} />
        A máquina fica ligada de qualquer jeito (o farm não aumenta a conta de luz)
      </label>
      {!marginal && (
        <div className="row">
          <label className="row">Consumo (W)<input value={watts} onChange={(e) => setWatts(e.target.value)} inputMode="decimal" style={{ width: "6rem" }} /></label>
          <label className="row">Tarifa (R$/kWh)<input value={kwh} onChange={(e) => setKwh(e.target.value)} inputMode="decimal" style={{ width: "6rem" }} /></label>
          <label className="row">Câmbio (R$ por US$)<input value={usd} onChange={(e) => setUsd(e.target.value)} inputMode="decimal" style={{ width: "6rem" }} /></label>
        </div>
      )}
      <p className="muted small" style={{ margin: 0 }}>
        A tarifa vem na conta de luz (total em R$ ÷ kWh do mês). Com algum campo vazio, o lucro sai sem o custo de energia.
      </p>
      <div className="row">
        <button type="submit" disabled={busy}>{busy ? "Salvando…" : "Salvar"}</button>
        {msg && <span className={`small ${msg === "salvo" ? "muted" : "error"}`}>{msg}</span>}
      </div>
    </form>
  );
}
