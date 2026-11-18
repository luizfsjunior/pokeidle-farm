"use client";

import Link from "next/link";
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
      <NowRow label="Captura" action={capture ? "Ver" : "Escolher"}
        value={capture
          ? <>{capture.species_name ?? `#${capture.species_id}`} <span className="muted num">{num(capture.captured)}{capture.count ? ` de ${num(capture.count)}` : ""}</span></>
          : <span className="muted">nenhuma</span>}>
        {capture
          ? <CaptureStatus accountId={accountId} active={capture} />
          : <p className="small" style={{ margin: 0 }}>Escolha a espécie na <Link href={`/pokedex?conta=${accountId}`}>Pokédex</Link> (botão Capturar).</p>}
      </NowRow>
    </section>
  );
}

function NowRow({ label, value, action, children }: { label: string; value: React.ReactNode; action: string; children: React.ReactNode }) {
  return (
    <details className="now-row">
      <summary>
        <span className="now-label">{label}</span>
        <span className="now-value">{value}</span>
        <span className="now-action">{action}</span>
      </summary>
      <div className="now-body">{children}</div>
    </details>
  );
}
