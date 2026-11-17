"use client";

import { useId, useState } from "react";
import { num } from "@/lib/format";

export type Point = { day: string; value: number | null };

/**
 * Linha de uma série só (pequenos múltiplos: um gráfico por medida, nunca dois eixos).
 * Hover e teclado (setas) movem a mira; o último valor fica escrito ao lado do título; a tabela
 * fica em "Ver valores". Ver a skill dataviz: marca de 2px, grade recessiva, sem legenda (série única).
 */
export function TrendChart({ title, points, tone, compact = false }: {
  title: string;
  points: Point[];
  tone: "accent" | "gold" | "gem" | "diamond" | "good";
  compact?: boolean;
}) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const data = points.filter((p): p is { day: string; value: number } => p.value != null);
  const W = 320, H = 120, PL = 6, PR = 6, PT = 10, PB = 20;
  if (data.length === 0) {
    return (
      <figure className="trend">
        <figcaption className="trend-head"><span>{title}</span></figcaption>
        <p className="muted small">Sem dados ainda: o histórico começa no dia em que o perfil foi gravado.</p>
      </figure>
    );
  }
  if (data.length === 1) {
    // um ponto só não é gráfico: o número e quando começa a linha
    return (
      <figure className={`trend trend-${tone} trend-single`}>
        <figcaption className="trend-head">
          <span>{title}</span>
          <span className="trend-value num">{num(data[0].value, { compact })}<span className="muted small"> hoje</span></span>
        </figcaption>
      </figure>
    );
  }
  const vals = data.map((d) => d.value);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08;
  lo -= pad; hi += pad;
  const x = (i: number) => PL + (data.length === 1 ? (W - PL - PR) / 2 : (i * (W - PL - PR)) / (data.length - 1));
  const y = (v: number) => PT + (1 - (v - lo) / (hi - lo)) * (H - PT - PB);
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`).join("");
  const last = data[data.length - 1];
  const first = data[0];
  const delta = last.value - first.value;
  const shown = hover ?? data.length - 1;
  const fmt = (v: number) => num(v, { compact });
  const dayLabel = (d: string) => d.slice(8, 10) + "/" + d.slice(5, 7);

  const pick = (clientX: number, rect: DOMRect) => {
    const px = ((clientX - rect.left) / rect.width) * W;
    let best = 0;
    for (let i = 1; i < data.length; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
    setHover(best);
  };

  return (
    <figure className={`trend trend-${tone}`}>
      <figcaption className="trend-head">
        <span>{title}</span>
        <span className="trend-value num">
          {fmt(data[shown].value)}
          <span className="muted small"> {hover == null ? "hoje" : dayLabel(data[shown].day)}</span>
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="trend-svg"
        role="img"
        aria-labelledby={`${id}-desc`}
        tabIndex={0}
        onPointerMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        onPointerLeave={() => setHover(null)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setHover(Math.max(0, (hover ?? data.length - 1) - 1));
          if (e.key === "ArrowRight") setHover(Math.min(data.length - 1, (hover ?? data.length - 1) + 1));
        }}
      >
        <desc id={`${id}-desc`}>
          {title}: de {fmt(first.value)} em {dayLabel(first.day)} para {fmt(last.value)} em {dayLabel(last.day)}
        </desc>
        <line x1={PL} x2={W - PR} y1={H - PB} y2={H - PB} className="trend-axis" />
        <path d={path} className="trend-line" />
        <circle cx={x(data.length - 1)} cy={y(last.value)} r={4} className="trend-dot" />
        {hover != null && (
          <>
            <line x1={x(hover)} x2={x(hover)} y1={PT} y2={H - PB} className="trend-cross" />
            <circle cx={x(hover)} cy={y(data[hover].value)} r={4} className="trend-dot" />
          </>
        )}
        <text x={PL} y={H - 5} className="trend-tick">{dayLabel(first.day)}</text>
        <text x={W - PR} y={H - 5} className="trend-tick" textAnchor="end">{dayLabel(last.day)}</text>
      </svg>
      <div className="trend-foot small muted">
        {data.length > 1 ? <>{delta >= 0 ? "+" : "−"}{fmt(Math.abs(delta))} em {data.length} dias</> : "1 dia"}
        <details>
          <summary>Ver valores</summary>
          <table className="trend-table">
            <tbody>
              {[...data].reverse().map((d) => (
                <tr key={d.day}><td>{dayLabel(d.day)}</td><td className="r num">{num(d.value)}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    </figure>
  );
}
