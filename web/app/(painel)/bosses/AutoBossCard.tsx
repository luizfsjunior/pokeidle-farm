"use client";

import { CommandStatus } from "@/components/CommandStatus";
import { BOSS_REGIONS, PRIZE_PT, PRIZES, bossLevel, type Prize } from "@/lib/bosses";
import { dateTime, num } from "@/lib/format";
import type { Profile } from "@/lib/profile";
import { usePanel } from "@/lib/query/hooks";
import { useCommand } from "@/lib/useCommand";

const TOKEN_ITEM = "70000"; // Bronze Boss Token (entrada de todos os bosses, bossesJogaveis do welcome)
const IDEAL = 5;
const mult = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

type BossConfig = { prize?: Prize; region?: string; dry_run?: boolean; max_mult?: number };
type BossRow = { enabled: boolean; config: BossConfig } | null;
type BossEvent = { type: string; received_at: string; data: Record<string, unknown> };

const REASON_PT: Record<string, string> = {
  ok: "pode lutar",
  sem_token: "sem Boss Token",
  equipe_fraca: "equipe abaixo do nível do boss",
  nivel_treinador: "treinador abaixo do nível da região",
  sem_catalogo: "esperando o catálogo do jogo",
  regiao_desconhecida: "região desconhecida",
};

/** penalidadeDaMinhaEquipe do app.js: força = Σ min(1, nível/teamLevel); dano tomado ×3^(5 − força). */
export function teamPenalty(levels: number[], teamLevel: number) {
  const force = levels.reduce((s, lv) => s + Math.min(1, lv / teamLevel), 0);
  return { force, mult: 3 ** Math.max(0, IDEAL - force) };
}

async function loadBossPlugin(sb: import("@supabase/supabase-js").SupabaseClient, accountId: string) {
  const [cfg, evs] = await Promise.all([
    sb.from("strategy_configs").select("enabled, config").eq("account_id", accountId).eq("plugin", "boss").maybeSingle(),
    sb.from("events").select("type, received_at, data").eq("account_id", accountId)
      .in("type", ["boss.plan", "boss.would", "boss.auto_set", "boss.entered", "boss.auto_off", "boss.blocked"])
      .order("received_at", { ascending: false }).limit(8),
  ]);
  return {
    row: (cfg.data ? { enabled: !!cfg.data.enabled, config: (cfg.data.config ?? {}) as BossConfig } : null) as BossRow,
    events: (evs.data ?? []) as BossEvent[],
  };
}

/**
 * Bosses automáticos (épico C4/C5): o plugin `boss` da conta, quantos tokens ela tem, se a equipe aguenta o boss
 * da região e o que o plugin decidiu por último. Desligado por padrão; ligado, começa em ensaio (só registra).
 */
export function AutoBossCard({ accountId, nick, profile }: { accountId: string; nick: string; profile: Profile }) {
  const q = usePanel(["boss-plugin", accountId], (sb) => loadBossPlugin(sb, accountId), { refetchInterval: 60_000 });
  const { send, cmd, error, busy } = useCommand();
  const row = q.data?.row ?? null;
  const cfg: BossConfig = row?.config ?? {};
  const on = !!row?.enabled;
  const dry = cfg.dry_run !== false;
  const prize: Prize = cfg.prize ?? "mega";

  const tokens = Number(profile.items?.[TOKEN_ITEM] ?? 0);
  const levels = profile.team.map((m) => m.level ?? 0);
  const trainer = profile.level ?? 0;
  const step = Math.max(0, BOSS_REGIONS.filter((_, i) => trainer >= bossLevel(i)).length - 1);
  const target = bossLevel(step);
  const pen = teamPenalty(levels, target);
  const missing = levels.filter((lv) => lv < target).length + Math.max(0, IDEAL - levels.length);
  const boss = (profile.extra?.boss ?? {}) as { auto?: boolean; autoKey?: string | null; arena?: unknown; vitorias?: Record<string, number> };
  const wins = Object.values(boss.vitorias ?? {}).reduce((s, n) => s + (Number(n) || 0), 0);
  const plan = q.data?.events.find((e) => e.type === "boss.plan");

  const set = (config: BossConfig, enabled = on) => void send(accountId, "plugin.set", { plugin: "boss", enabled, config: { ...cfg, ...config } });

  return (
    <section className="card auto-boss">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Bosses automáticos · {nick}</h2>
        <label className="row">
          <input type="checkbox" role="switch" checked={on} disabled={busy} onChange={(e) => set({}, e.target.checked)} />
          {on ? <span className="good-text small">{dry ? "ligado em ensaio" : "ligado"}</span> : <span className="muted small">desligado</span>}
        </label>
      </div>
      <p className="small muted" style={{ margin: ".3rem 0 .8rem" }}>
        Luta no boss que dá o prêmio escolhido hoje, na região mais alta em que a conta entra e a equipe aguenta, enquanto houver
        Boss Token. Em ensaio só registra o que faria (o protocolo do boss ainda não foi visto ao vivo).
      </p>
      <div className="auto-boss-grid small">
        <div>
          <div className="muted">Tokens</div>
          <strong className="num">{num(tokens)}</strong>
        </div>
        <div>
          <div className="muted">Equipe no {BOSS_REGIONS[step].name} (nv {num(target)})</div>
          <strong className={pen.mult <= 1 ? "good-text" : "warn-text"}>
            {IDEAL - missing} de {IDEAL} no nível · dano ×{mult.format(pen.mult)}
          </strong>
        </div>
        <div>
          <div className="muted">Repetição no jogo</div>
          <strong>{boss.auto ? `ligada (${boss.autoKey ?? "?"})` : "desligada"}</strong>{wins > 0 && <span className="muted"> · {num(wins)} vitórias</span>}
        </div>
        <div>
          <div className="muted">Última decisão</div>
          {plan ? (
            <strong title={dateTime(plan.received_at)}>
              {String(plan.data.name ?? "nenhum boss")}: {REASON_PT[String(plan.data.reason)] ?? String(plan.data.reason)}
            </strong>
          ) : <span className="muted">{on ? "esperando o primeiro minuto" : "—"}</span>}
        </div>
      </div>
      <div className="row" style={{ gap: ".6rem", marginTop: ".8rem", flexWrap: "wrap" }}>
        <label className="small">Prêmio{" "}
          <select value={prize} disabled={busy} onChange={(e) => set({ prize: e.target.value as Prize })}>
            {PRIZES.map((p) => <option key={p} value={p}>{PRIZE_PT[p]}</option>)}
          </select>
        </label>
        <label className="small row">
          <input type="checkbox" checked={dry} disabled={busy} onChange={(e) => set({ dry_run: e.target.checked })} /> Ensaio (só registrar)
        </label>
        <CommandStatus cmd={cmd} error={error} inline />
      </div>
      {(q.data?.events.length ?? 0) > 0 && (
        <details style={{ marginTop: ".6rem" }}>
          <summary className="small muted">Registro do plugin</summary>
          <ul className="small" style={{ margin: ".4rem 0 0", paddingLeft: "1rem" }}>
            {q.data!.events.map((e, i) => (
              <li key={i}><span className="muted">{dateTime(e.received_at)}</span> {e.type} {eventText(e)}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function eventText(e: BossEvent): string {
  const d = e.data;
  if (e.type === "boss.plan") return `${String(d.name ?? "—")}: ${REASON_PT[String(d.reason)] ?? String(d.reason)}`;
  if (e.type === "boss.would") return `faria ${String(d.step)} ${JSON.stringify(d.wire)}`;
  if (e.type === "boss.blocked") return `${String(d.step)}: ${String(d.reason)}`;
  return JSON.stringify(d);
}
