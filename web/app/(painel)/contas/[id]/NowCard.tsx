"use client";

import Link from "next/link";
import { useState } from "react";
import { Alerts } from "@/components/Alerts";
import { CaptureStatus, type ActiveCapture } from "@/components/Capture";
import { HuntPicker, type HuntHold, type HuntOption } from "@/components/HuntPicker";
import type { Alert } from "@/lib/alerts";
import { dateTime, num } from "@/lib/format";
import type { Mon } from "@/lib/profile";
import { currentMode, MODE_LABEL, ModeForm } from "./FocusCard";
import type { PluginRow } from "./data";

/**
 * "Fazendo agora" (docs/design/refatoracao-2026-11-20.md, 4.1): o modo (o que a conta faz sozinha), o desvio
 * por cima dele (captura de uma espécie ou hunt manual, um de cada vez, que termina e volta ao modo), a hunt e
 * o treino da equipe. Cada linha abre a ação dela.
 */
export function NowCard({ accountId, plugins, capture, hold, hunts, huntSlug, trainerLevel, enabled, team, activeId, alerts }: {
  accountId: string;
  plugins: PluginRow[];
  capture: ActiveCapture | null;
  hold: HuntHold;
  hunts: HuntOption[];
  huntSlug: string | null;
  trainerLevel: number | null;
  enabled: boolean;
  team: Mon[];
  activeId: number | null;
  alerts?: Alert[];
}) {
  const mode = currentMode(plugins);
  const hunt = hunts.find((h) => h.slug === huntSlug);
  const holding = hold && new Date(hold.until) > new Date() ? hold : null;
  const holdName = holding ? hunts.find((h) => h.slug === holding.slug)?.name ?? holding.slug : null;
  const back = `depois volta ao ${MODE_LABEL[mode.mode]}`;
  return (
    <section className="card now-card">
      <h2>Fazendo agora</h2>
      <Alerts items={alerts} />
      <NowRow label="Modo" action="Mudar"
        value={<>{mode.label}{mode.warn && <span className="warn-text small"> · {mode.warn}</span>}</>}>
        <ModeForm key={mode.label} accountId={accountId} plugins={plugins} teamSize={team.length} />
      </NowRow>

      {capture ? (
        <NowRow label="Desvio" action="Ver"
          value={<>Capturando {capture.species_name ?? `#${capture.species_id}`}{" "}
            <span className="muted num">{num(capture.captured)}{capture.count ? ` de ${num(capture.count)}` : ""}</span>
            <span className="muted small"> · {back}</span></>}>
          <CaptureStatus accountId={accountId} active={capture} />
        </NowRow>
      ) : (
        <NowRow label="Desvio" action={holding ? "Mudar" : "Escolher hunt"}
          value={holding
            ? <>Hunt manual: {holdName} <span className="muted small">até {dateTime(holding.until)} · {back}</span></>
            : <span className="muted">nenhum: o modo escolhe a hunt</span>}>
          <HuntPicker key={`${hold?.slug}:${huntSlug}`} accountId={accountId} hunts={hunts} current={huntSlug} hold={hold}
            trainerLevel={trainerLevel} enabled={enabled} />
          <p className="small muted" style={{ margin: ".6rem 0 0" }}>
            Para capturar uma espécie, escolha na <Link href={`/pokedex?conta=${accountId}`}>Pokédex</Link>. Começar um desvio
            encerra o outro.
          </p>
        </NowRow>
      )}

      <div className="now-row now-static">
        <span className="now-label">Hunt</span>
        <span className="now-value">{hunt?.name ?? huntSlug ?? "—"}{hunt && <span className="muted num"> nv {num(hunt.level)}</span>}</span>
      </div>

      {mode.mode === "xp" && mode.train.on && <TrainRow team={team} activeId={activeId} target={mode.train.target} />}
    </section>
  );
}

/** Quem está treinando e quantos já chegaram no alvo (a mesma regra do plugin team_train). */
function TrainRow({ team, activeId, target }: { team: Mon[]; activeId: number | null; target: number }) {
  const below = team.filter((m) => (m.level ?? 0) < target);
  const active = team.find((m) => m.id === activeId);
  const training = active && (active.level ?? 0) < target
    ? active
    : [...below].sort((a, b) => (a.level ?? 0) - (b.level ?? 0) || (a.slot ?? 0) - (b.slot ?? 0))[0];
  const done = team.length - below.length;
  return (
    <div className="now-row now-static">
      <span className="now-label">Treino</span>
      <span className="now-value">
        {training
          ? <>{training.nickname || training.name || `#${training.id}`} <span className="muted num">nv {num(training.level ?? 0)} → {num(target)}</span>
            {training.id !== activeId && <span className="muted small"> · espera uma hunt segura para virar o ativo</span>}</>
          : <>equipe pronta</>}
        <span className="muted small"> · {done} de {team.length} no {num(target)}</span>
      </span>
    </div>
  );
}

/** Linha que abre a ação dela; aberta, o botão vira "Fechar". */
function NowRow({ label, value, action, children }: { label: string; value: React.ReactNode; action: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="now-row" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary aria-label={`${label}: ${open ? "fechar" : action.toLowerCase()}`}>
        <span className="now-label">{label}</span>
        <span className="now-value">{value}</span>
        <span className="now-action">{open ? "Fechar ✕" : action}</span>
      </summary>
      <div className="now-body">{children}</div>
    </details>
  );
}
