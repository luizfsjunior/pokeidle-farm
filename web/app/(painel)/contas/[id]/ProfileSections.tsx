"use client";

import { useState } from "react";
import { ItemIcon } from "@/components/ItemIcon";
import { MonSheet } from "@/components/MonSheet";
import { Sprite } from "@/components/Sprite";
import { num } from "@/lib/format";
import { gameDay, type Mon, type Profile } from "@/lib/profile";
import { BALL_ICONS, BALL_NAMES, GAME_SITE, itemIconUrl, type Atlas } from "@/lib/sprites";
import { MonActions } from "./TeamControls";

export type ItemInfo = { name: string; category: string | null; icon: string | null };

/** Equipe, coleção e mochila da conta, do `account_profile`. */
export function ProfileSections({ profile, atlas, looktypes, items, part = "all", accountId }: {
  part?: "all" | "status" | "collection";
  accountId?: string; // com ele, os botões de equipe (tornar ativo, pôr e tirar)
  profile: Profile;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  items: Map<string, ItemInfo>;
}) {
  const bag = Object.entries(profile.items)
    .map(([id, qty]) => ({ id, qty, info: items.get(id) }))
    .sort((a, b) => (a.info?.category ?? "~").localeCompare(b.info?.category ?? "~") || b.qty - a.qty);
  const balls = Object.entries(profile.balls).sort(([a], [b]) => Number(a) - Number(b));
  const highlights = profile.top_pokemon.filter((m) => !profile.team.some((t) => t.id === m.id)).slice(0, 12);

  const [open, setOpen] = useState<Mon | null>(null);
  // a ficha lê a versão mais nova do pokémon (o perfil recarrega a cada minuto)
  const all = [...profile.team, ...profile.top_pokemon, ...profile.shinies];
  const sheetMon = open ? all.find((m) => m.id === open.id) ?? open : null;
  const pass = profile.extra?.passe;
  const ex = profile.extra ?? {};
  return (
    <>
      {part !== "collection" && pass?.degrau != null && (
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

      {part !== "collection" && <ExtrasCard ex={ex} />}
      {part !== "status" && (<>

      <section className="card">
        <h2>Equipe</h2>
        {profile.team.length === 0 ? (
          <p className="muted small">Nenhum pokémon na equipe.</p>
        ) : (
          <div className="mons">
            {profile.team.map((m) => (
              <MonTile key={m.id} mon={m} atlas={atlas} looktypes={looktypes} active={m.id === profile.active_pokemon_id} onOpen={setOpen}>
                {accountId && <MonActions accountId={accountId} mon={m} team={profile.team} isActive={m.id === profile.active_pokemon_id} />}
              </MonTile>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Coleção</h2>
        <div className="collection">
          <Figure value={profile.pokemon_count} label="pokémons" />
          <Figure value={profile.shiny_count} label="shiny" />
          <Figure value={profile.dex_caught} label="espécies capturadas" />
          <Figure value={profile.dex_seen} label="espécies vistas" />
        </div>
        {highlights.length > 0 && (
          <>
            <h3>Mais fortes fora da equipe</h3>
            <div className="mons mons-small">
              {highlights.map((m) => (
                <MonTile key={m.id} mon={m} atlas={atlas} looktypes={looktypes} small onOpen={setOpen}>
                  {accountId && <MonActions accountId={accountId} mon={m} team={profile.team} isActive={false} />}
                </MonTile>
              ))}
            </div>
          </>
        )}
        {profile.shinies.length > 0 && (
          <>
            <h3>Shinies</h3>
            <div className="mons mons-small">
              {profile.shinies.map((m) => <MonTile key={m.id} mon={m} atlas={atlas} looktypes={looktypes} small onOpen={setOpen} />)}
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h2>Mochila</h2>
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
            {bag.map(({ id, qty, info }) => (
              <li key={id} title={info?.category ?? undefined}>
                <ItemIcon src={itemIconUrl(info?.icon)} name={info?.name ?? id} />
                <span className="bag-name">{info?.name ?? `Item #${id}`}</span>
                <span className="bag-qty num">{num(qty)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      </>)}
      {sheetMon && (
        <MonSheet mon={sheetMon} atlas={atlas} looktypes={looktypes} active={sheetMon.id === profile.active_pokemon_id} onClose={() => setOpen(null)}>
          {accountId && (
            <MonActions accountId={accountId} mon={sheetMon} team={profile.team} isActive={sheetMon.id === profile.active_pokemon_id} />
          )}
        </MonSheet>
      )}
    </>
  );
}

function MonTile({ mon, atlas, looktypes, active, small, children, onOpen }: {
  children?: React.ReactNode;
  onOpen?: (m: Mon) => void;
  mon: Mon;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  active?: boolean;
  small?: boolean;
}) {
  const hp = mon.hp != null && mon.max_hp ? Math.max(0, Math.min(1, mon.hp / mon.max_hp)) : null;
  return (
    <div className={`mon ${active ? "is-active" : ""} ${mon.shiny ? "is-shiny" : ""}`}>
      <button type="button" className="mon-open" onClick={() => onOpen?.(mon)} aria-label={`Ver a ficha de ${mon.name ?? "pokémon"}`}>
        <Sprite mon={mon} atlas={atlas} looktypes={looktypes} size={small ? 48 : 72} />
        <span className="mon-name">
          {mon.name ?? `#${mon.species_id ?? "?"}`}
          {mon.shiny && <span aria-label="shiny" title="Shiny"> ✨</span>}
        </span>
        <span className="mon-meta num">nv {mon.level ?? "?"}{mon.power != null && <> · poder {num(mon.power, { compact: true })}</>}</span>
        {!small && (
          <span className="mon-meta num muted">
            {mon.potency != null && <>P{mon.potency} · </>}
            {mon.iv_sum != null && <>IV {mon.iv_sum}</>}
            {mon.quality != null && <> · Q {num(mon.quality)}</>}
            {active && <> · ativo</>}
          </span>
        )}
      </button>
      {!small && hp != null && (
        <div className="hpbar" aria-label={`HP ${Math.round(hp * 100)}%`}>
          <span style={{ width: `${hp * 100}%` }} className={hp < 0.3 ? "low" : undefined} />
        </div>
      )}
      {children}
    </div>
  );
}

function Figure({ value, label }: { value: number; label: string }) {
  return (
    <div className="figure">
      <span className="figure-value num">{num(value)}</span>
      <span className="figure-label">{label}</span>
    </div>
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
