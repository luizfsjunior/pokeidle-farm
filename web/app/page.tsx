import { CommandButtons } from "@/components/CommandButtons";
import { Shell } from "@/components/Shell";
import { requireUser } from "@/lib/supabase/server";
import { ago, num, todaySP } from "@/lib/format";
import { STATUS_LABEL, type Account } from "@/lib/types";

export const dynamic = "force-dynamic";

const TODAY_METRICS = ["kills", "xp", "gold", "gold_net", "captures", "capture_attempts", "active_minutes"] as const;
type Totals = Record<(typeof TODAY_METRICS)[number], number>;

export default async function Overview() {
  const { supabase, email } = await requireUser();
  const today = todaySP();

  const [accountsRes, dailyRes] = await Promise.all([
    supabase.from("accounts").select("id, nick, role, enabled, status").order("role").order("nick"),
    supabase.from("metric_daily").select("account_id, metric, value").eq("day", today).in("metric", [...TODAY_METRICS]),
  ]);
  const accounts = (accountsRes.data ?? []) as Account[];

  const lastSeen = new Map<string, string>();
  await Promise.all(
    accounts.map(async (a) => {
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
      <p className="secondary small">Hoje ({today.split("-").reverse().join("/")}), por hora ativa. A métrica é recalculada a cada 10 min.</p>
      {err && <p className="error">Erro ao ler o Supabase: {err}</p>}
      {accounts.length === 0 && !err && (
        <div className="card">Nenhuma conta cadastrada para este usuário. Veja <code>docs/deploy.md</code>.</div>
      )}
      <div className="grid">
        {accounts.map((a) => {
          const t = totals.get(a.id);
          const mins = t?.active_minutes ?? 0;
          return (
            <section key={a.id} className="card">
              <div className="spread">
                <h2 style={{ margin: 0 }}>{a.nick}</h2>
                <span className={`badge ${a.status}`}>{STATUS_LABEL[a.status] ?? a.status}</span>
              </div>
              <div className="muted small">
                {a.role === "farm" ? "farm" : "pessoal"}
                {!a.enabled && " · desativada"} · último evento {ago(lastSeen.get(a.id))}
              </div>
              <div className="stats">
                <Stat label="Abates/h" value={num(perHour(t?.kills ?? 0, mins))} />
                <Stat label="XP/h" value={num(perHour(t?.xp ?? 0, mins), { compact: true })} />
                <Stat label="Gold/h" value={num(perHour(t?.gold ?? 0, mins), { compact: true })} />
                <Stat label="Gold líquido/h" value={num(perHour(t?.gold_net ?? 0, mins), { compact: true })} />
                <Stat label="Capturas/h" value={num(perHour(t?.captures ?? 0, mins))} />
                <Stat label="Taxa de captura" value={t?.capture_attempts ? `${num((t.captures * 100) / t.capture_attempts)}%` : "—"} />
                <Stat label="Tempo ativo" value={mins ? `${num(mins / 60)} h` : "—"} />
              </div>
              <CommandButtons account={a} />
            </section>
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
