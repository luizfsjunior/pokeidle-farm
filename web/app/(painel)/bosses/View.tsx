"use client";

import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { LdBlock } from "@/components/Loading";
import { MonSheet } from "@/components/MonSheet";
import { AccountPicker } from "@/components/AccountPicker";
import { ErrorNote, PageHeader } from "@/components/Page";
import { Matchups, Moves, StatRadar, TypeChips } from "@/components/SpeciesFacts";
import { Sprite } from "@/components/Sprite";
import {
  BOSS_REGIONS, PRIZE_PT, bossLevel, candidates, loadBossSpecies, loadTypes, nextRotation, prizeAt, prizeChances,
  type BossSpecies, type Candidate,
} from "@/lib/bosses";
import { dateTime, num, pct } from "@/lib/format";
import { loadGameRules, loadSpeciesInfo, type GameRules, RULES_VERSION } from "@/lib/pokemon";
import { loadProfiles, type Mon, type Profile } from "@/lib/profile";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import type { Atlas } from "@/lib/sprites";

const mult = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const TEAM_SIZE = 5;

/** Bosses lendários: stats, fraquezas, prêmio do dia e quem da conta serve contra cada um. */
export function BossesView() {
  const sp = useSearchParams();
  const accountsQ = useAccounts();
  const accounts = useMemo(() => (accountsQ.data ?? []).filter((a) => a.role === "farm"), [accountsQ.data]);
  const profiles = usePanel(["boss-profiles", accounts.map((a) => a.id).join(",")], (sb) => loadProfiles(sb, accounts.map((a) => a.id)),
    { enabled: accounts.length > 0, refetchInterval: 60_000 }).data;
  // sem escolha: a conta de nível mais alto (a que está mais perto dos bosses)
  const chosen = accounts.find((a) => a.id === sp.get("conta"))
    ?? [...accounts].sort((a, b) => (profiles?.get(b.id)?.level ?? 0) - (profiles?.get(a.id)?.level ?? 0))[0] ?? null;
  const profile = chosen ? profiles?.get(chosen.id) : undefined;
  const species = usePanel(["boss-species"], loadBossSpecies, { staleTime: 30 * 60_000 });
  const { data: rules } = usePanel(["game-rules", RULES_VERSION], loadGameRules, { staleTime: 30 * 60_000 });
  const { data: atlas = null } = useAtlas();

  const mons = useMemo(() => {
    if (!profile) return [];
    const seen = new Map<number, Mon>();
    for (const m of [...profile.team, ...profile.top_pokemon]) seen.set(m.id, m);
    return [...seen.values()];
  }, [profile]);
  const speciesIds = [...new Set(mons.map((m) => m.species_id).filter((x): x is number => x != null))].sort((a, b) => a - b);
  const types = usePanel(["mon-types", speciesIds.join(",")], (sb) => loadTypes(sb, speciesIds), { enabled: speciesIds.length > 0, staleTime: 30 * 60_000 }).data;

  const trainer = profile?.level ?? 0;
  const reachable = BOSS_REGIONS.filter((_, i) => trainer >= bossLevel(i)).length;
  const [regionPick, setRegion] = useState<number | null>(null);
  const region = regionPick ?? Math.max(0, reachable - 1);

  return (
    <>
      <PageHeader title="Bosses" hint={<>
        Cada região tem um trio fixo de lendários. A região pede um nível mínimo, e cada luta gasta 1 Boss Token. O prêmio de cada boss
        do trio gira todo dia às 18:00 de Brasília (TM, fragmento de Mega, tickets). O dano que você leva sobe ×3 por degrau abaixo do nível do
        boss: o ideal são 5 pokémons no nível dele ou acima. Fraquezas e &quot;quem serve&quot; supõem que os golpes do boss saem no tipo dele.
      </>}>
        <AccountPicker all={false} accounts={accounts} chosen={chosen?.id ?? null} hasParam={sp.has("conta")} href={(id) => `/bosses?conta=${id}`} />
      </PageHeader>
      <ErrorNote message={species.error?.message} />

      <div className="segmented boss-regions" role="radiogroup" aria-label="Região">
        {BOSS_REGIONS.map((r, i) => (
          <button key={r.region} type="button" role="radio" aria-checked={region === i} className={region === i ? "on" : undefined} onClick={() => setRegion(i)}>
            {r.name} <span className={`num small ${i < reachable ? "good-text" : "muted"}`}>{num(bossLevel(i))}</span>
          </button>
        ))}
      </div>
      <p className="small muted" style={{ margin: ".5rem 0 1rem" }}>
        {BOSS_REGIONS[region].trio} · pede nível {num(bossLevel(region))}
        {profile && <> · {chosen?.nick} está no nível {num(trainer)}{trainer >= bossLevel(region) ? " e pode lutar" : `: faltam ${num(bossLevel(region) - trainer)}`}</>}
        {" · "}o prêmio gira {dateTime(new Date(nextRotation()).toISOString())}
      </p>

      {!species.data || !rules ? <LdBlock h={420} /> : (
        <div className="boss-grid">
          {BOSS_REGIONS[region].ids.map((id, pos) => {
            const boss = species.data.get(id);
            if (!boss) return null;
            return (
              <BossCard key={id} boss={boss} step={region} pos={pos} rules={rules} atlas={atlas} profile={profile}
                list={types ? candidates(mons, types, boss, bossLevel(region), rules) : []} />
            );
          })}
        </div>
      )}
    </>
  );
}

function BossCard({ boss, step, pos, rules, atlas, profile, list }: {
  boss: BossSpecies; step: number; pos: number; rules: GameRules; atlas: Atlas | null; profile: Profile | undefined; list: Candidate[];
}) {
  const info = usePanel(["species-info", boss.species_id], (sb) => loadSpeciesInfo(sb, boss.species_id), { staleTime: 30 * 60_000 }).data;
  const [open, setOpen] = useState<Mon | null>(null);
  const prize = prizeAt(pos);
  const ch = prizeChances(step);
  const level = bossLevel(step);
  const ready = list.filter((c) => c.levelOk).length;
  const mon = { id: boss.species_id, species_id: boss.species_id, name: boss.name, looktype: boss.looktype ?? undefined };

  return (
    <section className="card boss-card">
      <div className="boss-head">
        <div className="drawer-stage"><Sprite mon={mon} atlas={atlas} size={80} /></div>
        <div>
          <h2 style={{ margin: 0 }}>{boss.name}</h2>
          <div className="sheet-types"><TypeChips s={boss} /></div>
          <div className="small" style={{ marginTop: ".3rem" }}>
            <span className="num">Nv {num(level)}</span> · hoje dá <b className={`prize prize-${prize}`}>{PRIZE_PT[prize]}</b>
          </div>
        </div>
      </div>

      <StatRadar base={info?.base ?? null} />

      <div>
        <h3>Tipos</h3>
        <Matchups s={boss} rules={rules} />
      </div>

      {profile && (
        <div>
          <div className="spread">
            <h3 style={{ margin: 0 }}>Da sua conta</h3>
            <span className={`small ${ready >= TEAM_SIZE ? "good-text" : "muted"}`}>{ready} de {TEAM_SIZE} no nível {num(level)}</span>
          </div>
          {list.length === 0 ? <p className="muted small">Sem pokémons no perfil ainda.</p> : (
            <ul className="boss-picks">
              {list.slice(0, 6).map((c) => (
                <li key={c.mon.id}>
                  <button type="button" className="boss-pick" onClick={() => setOpen(c.mon)}>
                    <Sprite mon={c.mon} atlas={atlas} size={36} />
                    <span className="bp-name">{c.mon.name}{c.mon.slot != null && <span className="muted small"> · equipe</span>}</span>
                    <span className={`bp-lv num small ${c.levelOk ? "good-text" : "warn-text"}`} title={c.levelOk ? "No nível do boss" : `Faltam ${num(level - (c.mon.level ?? 0))} níveis`}>
                      nv {num(c.mon.level ?? null)}
                    </span>
                    <span className={`bp-mult bp-hits ${c.hits >= 2 ? "good" : c.hits < 1 ? "bad" : ""}`} title="Quanto os tipos dele batem no boss">bate ×{mult.format(c.hits)}</span>
                    <span className={`bp-mult bp-takes ${c.takes <= 0.5 ? "good" : c.takes >= 2 ? "bad" : ""}`} title="O pior que ele leva dos tipos do boss">leva ×{mult.format(c.takes)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <details className="stat-table">
        <summary>Golpes e prêmios</summary>
        <p className="small" style={{ margin: ".2rem 0 .6rem" }}>
          Por vitória: TM {pct(ch.tm)} · fragmento de Mega {pct(ch.mega, 2)} · fragmento de Mega shiny {pct(ch.megaShiny, 2)}.
          O prêmio do dia diz qual desses o boss solta hoje.
        </p>
        {info && <Moves attacks={info.attacks} />}
      </details>

      {open && (
        <MonSheet mon={open} atlas={atlas} looktypes={new Map()} active={open.id === profile?.active_pokemon_id} onClose={() => setOpen(null)} />
      )}
    </section>
  );
}
