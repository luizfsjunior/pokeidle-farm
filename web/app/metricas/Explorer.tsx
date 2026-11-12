"use client";

import { useEffect, useMemo, useState } from "react";
import { LineChart, type Point } from "@/components/LineChart";
import { num } from "@/lib/format";
import { createClient } from "@/lib/supabase/client";
import type { Account, MetricDef } from "@/lib/types";

const RANGES = {
  "24h": { label: "Últimas 24 h", hours: 24, bucket: "hour" },
  "7d-h": { label: "7 dias, por hora", hours: 24 * 7, bucket: "hour" },
  "7d": { label: "7 dias, por dia", hours: 24 * 7, bucket: "day" },
  "30d": { label: "30 dias, por dia", hours: 24 * 30, bucket: "day" },
} as const;
type RangeKey = keyof typeof RANGES;

export function Explorer({ defs, accounts, hunts }: { defs: MetricDef[]; accounts: Account[]; hunts: string[] }) {
  const supabase = useMemo(() => createClient(), []);
  const [metric, setMetric] = useState(defs.find((d) => d.key === "kills_per_hour")?.key ?? defs[0]?.key ?? "");
  const [range, setRange] = useState<RangeKey>("24h");
  const [account, setAccount] = useState("");
  const [hunt, setHunt] = useState("");
  const [points, setPoints] = useState<Point[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const def = defs.find((d) => d.key === metric);
  const r = RANGES[range];

  useEffect(() => {
    if (!def) return;
    let cancelled = false;
    const to = new Date();
    const from = new Date(to.getTime() - r.hours * 3600_000);
    if (r.bucket === "hour") from.setUTCMinutes(0, 0, 0);
    setLoading(true);
    supabase
      .rpc("metric_series", {
        p_metric: metric,
        p_from: from.toISOString(),
        p_to: to.toISOString(),
        p_bucket: r.bucket,
        p_account: account || null,
        p_hunt: hunt || null,
      })
      .then(({ data, error }) => {
        if (cancelled) return;
        setLoading(false);
        if (error) { setError(error.message); setPoints([]); return; }
        setError(null);
        const rows = (data ?? []) as { bucket: string; value: number | null }[];
        const byTime = new Map(rows.map((x) => [new Date(x.bucket).getTime(), x.value === null ? null : Number(x.value)]));
        if (r.bucket === "hour") {
          // Completa as horas vazias: base = 0, razão = sem dado.
          const filled: Point[] = [];
          for (let t = from.getTime(); t <= to.getTime(); t += 3600_000) {
            filled.push({ t: new Date(t).toISOString(), v: byTime.has(t) ? byTime.get(t)! : def.kind === "base" ? 0 : null });
          }
          setPoints(filled);
        } else {
          setPoints(rows.map((x) => ({ t: x.bucket, v: x.value === null ? null : Number(x.value) })));
        }
      });
    return () => { cancelled = true; };
  }, [supabase, metric, range, account, hunt, def, r]);

  // Resumo do período: soma (base) ou razão das somas (nunca média de médias).
  const [summary, setSummary] = useState<{ label: string; value: number | null } | null>(null);
  useEffect(() => {
    if (!def) return;
    const sum = (ps: Point[]) => ps.reduce((a, p) => a + (p.v ?? 0), 0);
    if (def.kind === "base") { setSummary({ label: "Total no período", value: sum(points) }); return; }
    let cancelled = false;
    const to = new Date();
    const from = new Date(to.getTime() - r.hours * 3600_000);
    if (r.bucket === "hour") from.setUTCMinutes(0, 0, 0);
    const total = (key: string) =>
      supabase.rpc("metric_series", {
        p_metric: key, p_from: from.toISOString(), p_to: to.toISOString(), p_bucket: "day",
        p_account: account || null, p_hunt: hunt || null,
      }).then(({ data }) => ((data ?? []) as { value: number }[]).reduce((a, x) => a + Number(x.value ?? 0), 0));
    Promise.all([total(def.numerator!), total(def.denominator!)]).then(([n, d]) => {
      if (!cancelled) setSummary({ label: "No período todo", value: d > 0 ? (n * Number(def.scale)) / d : null });
    });
    return () => { cancelled = true; };
  }, [supabase, points, def, r, account, hunt]);

  return (
    <div className="card">
      <div className="filters">
        <label>Métrica
          <select value={metric} onChange={(e) => setMetric(e.target.value)}>
            <optgroup label="Ritmos e taxas">
              {defs.filter((d) => d.kind === "ratio").map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
            </optgroup>
            <optgroup label="Totais">
              {defs.filter((d) => d.kind === "base").map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
            </optgroup>
          </select>
        </label>
        <label>Período
          <select value={range} onChange={(e) => setRange(e.target.value as RangeKey)}>
            {Object.entries(RANGES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </label>
        <label>Conta
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">Todas</option>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.nick}</option>)}
          </select>
        </label>
        <label>Hunt
          <select value={hunt} onChange={(e) => setHunt(e.target.value)}>
            <option value="">Todas</option>
            {hunts.map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
        </label>
        {loading && <span className="muted small">carregando…</span>}
      </div>

      <div className="spread">
        <h2>{def?.label} <span className="muted small">({def?.unit})</span></h2>
        {summary && <span className="secondary small">{summary.label}: <strong className="num">{num(summary.value)} {def?.unit}</strong></span>}
      </div>
      {def?.description && <p className="muted small" style={{ marginTop: 0 }}>{def.description}</p>}
      {error ? <p className="error">{error}</p> : <LineChart points={points} bucket={r.bucket} unit={def?.unit ?? ""} label={def?.label ?? ""} />}
    </div>
  );
}
