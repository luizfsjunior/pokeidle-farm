"use client";

import Link from "next/link";
import { useState } from "react";
import { CaptureStatus, type ActiveCapture } from "@/components/Capture";
import { HuntPicker, type HuntHold, type HuntOption } from "@/components/HuntPicker";
import { dateTime, num } from "@/lib/format";
import { currentFocus, FocusForm } from "./FocusCard";
import type { PluginRow } from "./data";

/**
 * "Fazendo agora" (docs/design/painel-ux-v2.md, seção 3): foco, hunt e captura numa lista curta. Cada linha
 * abre a ação dela (mudar o foco, trocar a hunt, parar a captura); antes isso ficava em 4 cards e 2 abas.
 */
export function NowCard({ accountId, plugins, capture, hold, hunts, huntSlug, trainerLevel, enabled }: {
  accountId: string;
  plugins: PluginRow[];
  capture: ActiveCapture | null;
  hold: HuntHold;
  hunts: HuntOption[];
  huntSlug: string | null;
  trainerLevel: number | null;
  enabled: boolean;
}) {
  const focus = currentFocus(plugins);
  const hunt = hunts.find((h) => h.slug === huntSlug);
  const holding = hold && new Date(hold.until) > new Date();
  return (
    <section className="card now-card">
      <h2>Fazendo agora</h2>
      <NowRow label="Foco" value={focus.label} action="Mudar">
        <FocusForm key={focus.label} accountId={accountId} plugins={plugins} />
      </NowRow>
      <NowRow label="Hunt" action="Trocar"
        value={<>{hunt?.name ?? huntSlug ?? "—"}{hunt && <span className="muted num"> nv {num(hunt.level)}</span>}
          {holding && <span className="muted small"> · travada até {dateTime(hold.until)}</span>}</>}>
        <HuntPicker key={`${hold?.slug}:${huntSlug}`} accountId={accountId} hunts={hunts} current={huntSlug} hold={hold}
          trainerLevel={trainerLevel} enabled={enabled} />
      </NowRow>
      {capture ? (
        <NowRow label="Captura" action="Ver"
          value={<>{capture.species_name ?? `#${capture.species_id}`} <span className="muted num">{num(capture.captured)}{capture.count ? ` de ${num(capture.count)}` : ""}</span></>}>
          <CaptureStatus accountId={accountId} active={capture} />
        </NowRow>
      ) : (
        // sem captura não há o que abrir aqui: a escolha é na Pokédex, então a linha leva direto para lá
        <Link href={`/pokedex?conta=${accountId}`} className="now-row now-link">
          <span className="now-label">Captura</span>
          <span className="now-value muted">nenhuma</span>
          <span className="now-action">Escolher na Pokédex →</span>
        </Link>
      )}
    </section>
  );
}

/** Linha que abre a ação dela; aberta, o botão vira "Fechar" (antes ficava "Mudar" e não dizia como sair). */
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
