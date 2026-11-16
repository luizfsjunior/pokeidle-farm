import { ItemIcon } from "@/components/ItemIcon";
import { Sprite } from "@/components/Sprite";
import { num } from "@/lib/format";
import { gameDay, type Mon, type Profile } from "@/lib/profile";
import { BALL_ICONS, BALL_NAMES, GAME_SITE, itemIconUrl, type Atlas } from "@/lib/sprites";

export type ItemInfo = { name: string; category: string | null; icon: string | null };

/** Equipe, coleção e mochila da conta, do `account_profile`. */
export function ProfileSections({ profile, atlas, looktypes, items }: {
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

  const pass = profile.extra?.passe;
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

      <section className="card">
        <h2>Equipe</h2>
        {profile.team.length === 0 ? (
          <p className="muted small">Nenhum pokémon na equipe.</p>
        ) : (
          <div className="mons">
            {profile.team.map((m) => (
              <MonTile key={m.id} mon={m} atlas={atlas} looktypes={looktypes} active={m.id === profile.active_pokemon_id} />
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
              {highlights.map((m) => <MonTile key={m.id} mon={m} atlas={atlas} looktypes={looktypes} small />)}
            </div>
          </>
        )}
        {profile.shinies.length > 0 && (
          <>
            <h3>Shinies</h3>
            <div className="mons mons-small">
              {profile.shinies.map((m) => <MonTile key={m.id} mon={m} atlas={atlas} looktypes={looktypes} small />)}
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
    </>
  );
}

function MonTile({ mon, atlas, looktypes, active, small }: {
  mon: Mon;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  active?: boolean;
  small?: boolean;
}) {
  const hp = mon.hp != null && mon.max_hp ? Math.max(0, Math.min(1, mon.hp / mon.max_hp)) : null;
  return (
    <div className={`mon ${active ? "is-active" : ""} ${mon.shiny ? "is-shiny" : ""}`}>
      <Sprite mon={mon} atlas={atlas} looktypes={looktypes} size={small ? 48 : 72} />
      <div className="mon-name">
        {mon.name ?? `#${mon.species_id ?? "?"}`}
        {mon.shiny && <span aria-label="shiny" title="Shiny"> ✨</span>}
      </div>
      <div className="mon-meta num">nv {mon.level ?? "?"}{mon.power != null && <> · poder {num(mon.power, { compact: true })}</>}</div>
      {!small && (
        <div className="mon-meta num muted">
          {mon.iv_sum != null && <>IV {mon.iv_sum}</>}
          {mon.quality != null && <> · nota {num(mon.quality)}</>}
          {active && <> · ativo</>}
        </div>
      )}
      {!small && hp != null && (
        <div className="hpbar" aria-label={`HP ${Math.round(hp * 100)}%`}>
          <span style={{ width: `${hp * 100}%` }} className={hp < 0.3 ? "low" : undefined} />
        </div>
      )}
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
