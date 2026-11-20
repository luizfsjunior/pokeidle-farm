"use client";

import { ItemIcon } from "@/components/ItemIcon";
import { num } from "@/lib/format";
import { gameDay, type Profile } from "@/lib/profile";
import { BALL_ICONS, BALL_NAMES, GAME_SITE, itemIconUrl } from "@/lib/sprites";

export type ItemInfo = { name: string; category: string | null; icon: string | null };
type RestockItem = { id: number; min?: number; target?: number };

/**
 * Passe e bônus (aba Agora) ou a mochila (aba Pokémons). A equipe e os destaques saíram: repetiam a lista de
 * pokémons (refatoracao-2026-11-20, 4.2).
 */
export function ProfileSections({ profile, items, part, restock = [] }: {
  part: "status" | "bag";
  profile: Profile;
  items: Map<string, ItemInfo>;
  restock?: RestockItem[]; // o que o restock mantém (mínimo e alvo por item)
}) {
  const bag = Object.entries(profile.items)
    .map(([id, qty]) => ({ id, qty, info: items.get(id) }))
    .sort((a, b) => (a.info?.category ?? "~").localeCompare(b.info?.category ?? "~") || b.qty - a.qty);
  const balls = Object.entries(profile.balls).sort(([a], [b]) => Number(a) - Number(b));
  const rules = new Map(restock.map((r) => [String(r.id), r]));
  const pass = profile.extra?.passe;
  const ex = profile.extra ?? {};
  if (part === "status") {
    return (
      <>
        {pass?.degrau != null && (
          <section className="card">
            <div className="spread">
              <h2 style={{ margin: 0 }}>Passe de batalha</h2>
              <span className={`small ${pass.ultimo === gameDay() ? "secondary" : "warn-text"}`}>
                {pass.ultimo === gameDay() ? "Prêmio de hoje resgatado" : "Prêmio de hoje ainda não resgatado"}
              </span>
            </div>
            <ol className="pass-track" aria-label={`Dia ${pass.degrau} de 30`}>
              {Array.from({ length: 30 }, (_, i) => (
                <li key={i} className={i < (pass.degrau ?? 0) ? "done" : undefined} title={`Dia ${i + 1}`} />
              ))}
            </ol>
            <p className="muted small" style={{ margin: ".5rem 0 0" }}>
              Dia {pass.degrau} de 30 · {num(pass.total ?? 0)} resgates · {num(pass.ciclos ?? 0)} trilhas completas
              {pass.vipAte && pass.vipAte > Date.now() ? " · trilha premium ativa" : ""}
            </p>
          </section>
        )}
        <ExtrasCard ex={ex} />
      </>
    );
  }
  return (
    <section className="card">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Mochila</h2>
        <span className="small muted">alvo = o que a reposição automática mantém</span>
      </div>
      {balls.length > 0 && (
        <ul className="bag bag-balls">
          {balls.map(([id, qty]) => (
            <li key={id}>
              <ItemIcon src={BALL_ICONS[id] ? GAME_SITE + BALL_ICONS[id] : null} name={BALL_NAMES[id] ?? `Ball ${id}`} />
              <span className="bag-name">{BALL_NAMES[id] ?? `Ball #${id}`}</span>
              <span className="bag-qty num">{num(qty)}</span>
            </li>
          ))}
        </ul>
      )}
      {bag.length === 0 ? (
        <p className="muted small">Mochila vazia.</p>
      ) : (
        <ul className="bag">
          {bag.map(({ id, qty, info }) => {
            const rule = rules.get(id);
            const stone = /stone$/i.test(info?.name ?? "") && !/fragment/i.test(info?.name ?? "");
            return (
              <li key={id} title={info?.category ?? undefined}>
                <ItemIcon src={itemIconUrl(info?.icon)} name={info?.name ?? id} />
                <span className="bag-name">
                  {info?.name ?? `Item #${id}`}
                  {rule?.target != null && <span className="small muted"> · alvo {num(rule.target)} (repõe abaixo de {num(rule.min ?? 0)})</span>}
                  {stone && <span className="small muted"> · vale ~2 gemas no Mercado</span>}
                </span>
                <span className={`bag-qty num ${rule?.min != null && qty < rule.min ? "warn-text" : ""}`}>{num(qty)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : {});
const n = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const pct = (mult: number) => `+${num((mult - 1) * 100)}%`;
const until = (ms: number | null) =>
  ms == null ? "" : new Date(ms).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const BONUS_NAME: Record<string, string> = { vip: "VIP", evento: "Evento", guild: "Guild", pocao: "Poção" };

/** Bônus ativos, evento, PvP, boss, chocadeira e Outland, do `extra` (formatos vistos em 16/11). */
function ExtrasCard({ ex }: { ex: Obj }) {
  const now = Date.now();
  const bonus = obj(ex.bonusXp);
  const parts = (Array.isArray(bonus.partes) ? bonus.partes : []).map(obj).filter((p) => (n(p.ate) ?? Infinity) > now);
  const ev = obj(ex.evento);
  const evOn = (n(ev.terminaEm) ?? 0) > now;
  const pvp = obj(ex.pvp);
  const boss = obj(ex.boss);
  const egg = obj(ex.chocadeira);
  const eggs = Array.isArray(egg.ovos) ? egg.ovos.length : null;
  const gyms = Array.isArray(ex.ginasios) ? ex.ginasios.length : null;
  const bossWins = Object.values(obj(boss.vitorias)).reduce<number>((s, v) => s + (n(v) ?? 0), 0);
  const tier = typeof pvp.tierId === "string" ? pvp.tierId : null;

  const items: { label: string; value: string; note?: string }[] = [];
  if (n(bonus.tr) != null) {
    items.push({
      label: "Bônus de XP",
      value: pct(n(bonus.tr)!),
      note: parts.map((p) => `${BONUS_NAME[String(p.id)] ?? String(p.id)} ${pct(n(p.tr) ?? 1)} até ${until(n(p.ate))}`).join(" · ") || undefined,
    });
  }
  if (evOn) {
    items.push({
      label: "Evento",
      value: `XP ${n(ev.xpTreinadorPct) != null ? `+${ev.xpTreinadorPct}%` : "—"}`,
      note: `farm +${n(ev.farmPct) ?? 0}% · termina ${until(n(ev.terminaEm))}`,
    });
  }
  if (tier) {
    items.push({
      label: "PvP",
      value: `${tier.charAt(0).toUpperCase()}${tier.slice(1)} ${String(pvp.divisaoNum ?? "")}`.trim(),
      note: `${num(n(pvp.vitorias) ?? 0)} V · ${num(n(pvp.derrotas) ?? 0)} D · ${num(n(pvp.pontos) ?? 0)} pontos`,
    });
  }
  if (Object.keys(boss).length) items.push({ label: "Boss", value: `${num(n(boss.pontos) ?? 0)} pontos`, note: `${num(bossWins)} vitórias` });
  if (eggs != null) items.push({ label: "Chocadeira", value: `${eggs} de ${num(n(egg.total) ?? 0)}`, note: eggs ? "ovos chocando" : "vazia" });
  if (gyms != null) items.push({ label: "Ginásios", value: num(gyms), note: "insígnias" });
  if (n(ex.outlandTier) != null) items.push({ label: "Outland", value: `tier ${num(n(ex.outlandTier))}` });
  if (n(ex.guildBonusPct)) items.push({ label: "Guild", value: `+${num(n(ex.guildBonusPct))}%`, note: n(ex.guildBonusRank) ? `rank ${ex.guildBonusRank}` : undefined });

  if (items.length === 0) return null;
  return (
    <section className="card">
      <h2>Bônus e progresso</h2>
      <div className="extras">
        {items.map((it) => (
          <div key={it.label} className="extra">
            <span className="figure-label">{it.label}</span>
            <span className="extra-value num">{it.value}</span>
            {it.note && <span className="small muted">{it.note}</span>}
          </div>
        ))}
      </div>
    </section>
  );
}
