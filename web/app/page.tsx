import { CommandButtons } from "@/components/CommandButtons";
import { Shell } from "@/components/Shell";
import { TrainerCard } from "@/components/TrainerCard";
import { loadProfiles, speciesOf } from "@/lib/profile";
import { loadAtlas, speciesLooktypes } from "@/lib/sprites";
import { rankLine } from "@/lib/rank";
import { requireUser } from "@/lib/supabase/server";
import { ago, num, todaySP } from "@/lib/format";
import { STATUS_LABEL, type Account } from "@/lib/types";

export const dynamic = "force-dynamic";

const TODAY_METRICS = [
  "kills", "xp", "gold", "gold_net", "captures", "capture_attempts", "active_minutes",
  "drops_value_orb", "drops_value_gold",
] as const;
type Totals = Record<(typeof TODAY_METRICS)[number], number>;

export default async function Overview() {
  const { supabase, email } = await requireUser();
  const today = todaySP();

  const [accountsRes, dailyRes, rankRes] = await Promise.all([
    supabase.from("accounts").select("id, nick, role, enabled, status").order("role").order("nick"),
    supabase.from("metric_daily").select("account_id, metric, value").eq("day", today).in("metric", [...TODAY_METRICS]),
    supabase.from("strategy_configs").select("account_id").eq("plugin", "rank").eq("enabled", true),
  ]);
  const accounts = (accountsRes.data ?? []) as Account[];
  const [profiles, atlas] = await Promise.all([loadProfiles(supabase, accounts.map((a) => a.id)), loadAtlas()]);
  const looktypes = await speciesLooktypes(supabase, speciesOf(...[...profiles.values()].map((p) => p.team)));

  const lastSeen = new Map<string, string>();
  const rankOn = new Set((rankRes.data ?? []).map((r) => r.account_id as string));
  const ranks = new Map<string, { species: number | null; target: string | null }>();
  await Promise.all(
    accounts.map(async (a) => {
      if (rankOn.has(a.id)) ranks.set(a.id, await rankLine(supabase, a.id));
      const { data } = await supabase
        .from("events").select("received_at").eq("account_id", a.id)
        .order("received_at", { ascending: false }).limit(1).maybeSingle();
      if (data) lastSeen.set(a.id, data.received_at as string);
    }),
  );

  const totals = new Map<string, Totals>();
  for (const r of dailyRes.data ?? []) {
    const t = totals.get(r.account_id) ?? (Object.fromEntries(TODAY_METRICS.map((m) => [m, 0])) as Totals);
    t[r.metric as keyof Totals] += Number(r.value);
    totals.set(r.account_id, t);
  }
  const perHour = (v: number, mins: number) => (mins > 0 ? (v * 60) / mins : null);

  const err = accountsRes.error?.message ?? dailyRes.error?.message;

  return (
    <Shell email={email}>
      <h1>Visão geral</h1>
      <p className="secondary small">Números de hoje ({today.split("-").reverse().join("/")}) recalculados a cada 10 min; moedas e equipe, a cada 2 min.</p>
      {err && <p className="error">Erro ao ler o Supabase: {err}</p>}
      {accounts.length === 0 && !err && (
        <div className="card">Nenhuma conta cadastrada para este usuário. Veja <code>docs/deploy.md</code>.</div>
      )}
      <div className="trainers">
        {accounts.map((a) => {
          const t = totals.get(a.id);
          const mins = t?.active_minutes ?? 0;
          const rank = ranks.get(a.id);
          return (
            <TrainerCard key={a.id} account={a} profile={profiles.get(a.id)} atlas={atlas} looktypes={looktypes}
              href={`/contas/${a.id}`}>
              <div className="today">
                <div className="today-title small secondary">
                  Hoje, por hora ativa{mins ? ` (${num(mins / 60)} h)` : ""} · último evento {ago(lastSeen.get(a.id))}
                </div>
                <div className="stats">
                  <Stat label="Drops em gemas" value={num(perHour(t?.drops_value_orb ?? 0, mins))} />
                  <Stat label="Abates" value={num(perHour(t?.kills ?? 0, mins))} />
                  <Stat label="XP" value={num(perHour(t?.xp ?? 0, mins), { compact: true })} />
                  <Stat label="Ouro" value={num(perHour(t?.gold ?? 0, mins), { compact: true })} />
                  <Stat label="Ouro líquido" value={num(perHour(t?.gold_net ?? 0, mins), { compact: true })} />
                  <Stat label="Capturas" value={num(perHour(t?.captures ?? 0, mins))} />
                  <Stat label="Taxa de captura" value={t?.capture_attempts ? `${num((t.captures * 100) / t.capture_attempts)}%` : "—"} />
                  <Stat label="Drops em ouro" value={num(perHour(t?.drops_value_gold ?? 0, mins), { compact: true })} />
                </div>
                {rank && (
                  <div className="small">
                    Rank: {num(rank.species ?? 0)} espécies na semana{rank.target && <>, alvo {rank.target}</>}
                  </div>
                )}
              </div>
              <CommandButtons account={a} />
            </TrainerCard>
          );
        })}
      </div>
    </Shell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}
