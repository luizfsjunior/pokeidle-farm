"use client";

import { useMemo, useRef, useState } from "react";
import { hourLabel, num } from "@/lib/format";

export type Point = { t: string; v: number | null };

const W = 760;
const H = 260;
const M = { top: 12, right: 16, bottom: 28, left: 56 };

function niceMax(max: number) {
  if (max <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(max));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= max) return m * p;
  return 10 * p;
}

/** Série única no tempo: linha 2px, crosshair + tooltip, tabela em <details>. */
export function LineChart({ points, bucket, unit, label }: { points: Point[]; bucket: "hour" | "day"; unit: string; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);

  const geo = useMemo(() => {
    const vals = points.map((p) => p.v).filter((v): v is number => v !== null);
    // gold_net pode ser negativo: o eixo inclui o zero e desce quando precisa.
    const yMax = niceMax(Math.max(0, ...vals));
    const yMin = -niceMax(Math.max(0, ...vals.map((v) => -v))) * (vals.some((v) => v < 0) ? 1 : 0);
    const iw = W - M.left - M.right;
    const ih = H - M.top - M.bottom;
    const x = (i: number) => M.left + (points.length <= 1 ? iw / 2 : (i * iw) / (points.length - 1));
    const y = (v: number) => M.top + ih - ((v - yMin) / (yMax - yMin)) * ih;
    // Quebra a linha onde não há valor (razão sem denominador).
    const segs: string[] = [];
    let cur = "";
    points.forEach((p, i) => {
      if (p.v === null) { if (cur) segs.push(cur); cur = ""; return; }
      cur += `${cur ? "L" : "M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`;
    });
    if (cur) segs.push(cur);
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => yMin + f * (yMax - yMin));
    const step = Math.max(1, Math.ceil(points.length / 7));
    const xTicks = points.map((_, i) => i).filter((i) => i % step === 0);
    return { x, y, segs, ticks, xTicks, ih };
  }, [points]);

  if (points.length === 0) return <p className="muted">Sem dados no período.</p>;

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = ref.current!.getBoundingClientRect();
    const sx = ((e.clientX - rect.left) / rect.width) * W;
    const iw = W - M.left - M.right;
    const i = points.length <= 1 ? 0 : Math.round(((sx - M.left) / iw) * (points.length - 1));
    setHover(Math.min(points.length - 1, Math.max(0, i)));
  }

  const hp = hover !== null ? points[hover] : null;

  return (
    <div className="chart">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label} por ${bucket === "hour" ? "hora" : "dia"}`}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <g className="axis">
          {geo.ticks.map((t) => (
            <g key={t}>
              <line className="gridline" x1={M.left} x2={W - M.right} y1={geo.y(t)} y2={geo.y(t)} />
              <text x={M.left - 8} y={geo.y(t) + 4} textAnchor="end">{num(t, { compact: true })}</text>
            </g>
          ))}
          {geo.xTicks.map((i) => (
            <text key={i} x={geo.x(i)} y={H - 8} textAnchor="middle">{hourLabel(points[i].t, bucket)}</text>
          ))}
        </g>
        {geo.segs.map((d, i) => <path key={i} className="line" d={d} />)}
        {points.length <= 40 && points.map((p, i) => p.v !== null && (
          <circle key={i} className="dot" cx={geo.x(i)} cy={geo.y(p.v)} r={4} />
        ))}
        {hp && (
          <g>
            <line className="cross" x1={geo.x(hover!)} x2={geo.x(hover!)} y1={M.top} y2={M.top + geo.ih} />
            {hp.v !== null && <circle className="dot" cx={geo.x(hover!)} cy={geo.y(hp.v)} r={5} />}
          </g>
        )}
      </svg>
      {hp && (
        <div className="tooltip" style={{ left: `${(geo.x(hover!) / W) * 100}%`, top: `${((hp.v !== null ? geo.y(hp.v) : M.top) / H) * 100}%` }}>
          <div className="muted">{hourLabel(hp.t, bucket)}</div>
          <strong>{hp.v === null ? "sem dado" : `${num(hp.v)} ${unit}`}</strong>
        </div>
      )}
      <details>
        <summary>Ver tabela</summary>
        <table>
          <thead><tr><th>{bucket === "hour" ? "Hora" : "Dia"}</th><th className="r">{label}</th></tr></thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.t}><td>{hourLabel(p.t, bucket)}</td><td className="r">{p.v === null ? "—" : num(p.v)}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
