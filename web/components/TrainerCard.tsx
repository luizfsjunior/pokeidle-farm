import Link from "next/link";
import { ago, num } from "@/lib/format";
import { activeMon, levelProgress, type Profile } from "@/lib/profile";
import type { Atlas } from "@/lib/sprites";
import { STATUS_LABEL, type Account } from "@/lib/types";
import { Sprite } from "./Sprite";

/** Cartão de treinador: o ativo em destaque, nick, nível, moedas e a equipe. */
export function TrainerCard({ account, profile, atlas, looktypes, href, wide = false, hideNick = false, children }: {
  account: Account;
  profile: Profile | undefined;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  href?: string;
  wide?: boolean;
  hideNick?: boolean; // a página da conta já tem o nick no título
  children?: React.ReactNode;
}) {
  const active = activeMon(profile);
  const progress = profile ? levelProgress(profile) : null;
  const vip = profile?.vip_until && new Date(profile.vip_until) > new Date();
  const ev = (profile?.extra?.evento ?? null) as { terminaEm?: number; xpTreinadorPct?: number } | null;
  const evOn = ev?.terminaEm != null && ev.terminaEm > Date.now();
  const nick = <span className="trainer-nick">{account.nick}</span>;

  return (
    <section className={`trainer ${wide ? "trainer-wide" : ""}`}>
      <div className="trainer-head">
        <div className="trainer-stage" title={active ? `${active.name ?? ""} nv ${active.level ?? "?"}` : undefined}>
          <Sprite mon={active} atlas={atlas} looktypes={looktypes} size={wide ? 112 : 80} />
        </div>
        <div className="trainer-id">
          <div className="trainer-title">
            {hideNick ? null : href ? <Link href={href}>{nick}</Link> : nick}
            <span className={`badge ${account.status}`}>{STATUS_LABEL[account.status] ?? account.status}</span>
          </div>
          <div className="trainer-level">
            <span>Nível <strong className="num">{profile?.level ?? "—"}</strong></span>
            {vip && <span className="tag-vip">VIP</span>}
            {evOn && (
              <span className="tag-event" title={`Evento até ${new Date(ev!.terminaEm!).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`}>
                Evento +{ev!.xpTreinadorPct ?? 0}% XP
              </span>
            )}
            {!account.enabled && <span className="muted">desligada</span>}
          </div>
          {progress != null && (
            <div className="xpbar" role="meter" aria-label="XP do nível" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)}>
              <span style={{ width: `${progress * 100}%` }} />
            </div>
          )}
          {active && (
            <div className="small secondary">
              Ativo: {active.name ?? `#${active.species_id}`}{active.shiny && " ✨"} · nv {active.level ?? "?"}
            </div>
          )}
        </div>
      </div>

      {profile ? (
        <>
          <div className="wallet">
            <Coin kind="gold" label="Ouro" value={profile.gold} />
            <Coin kind="gem" label="Gemas" value={profile.gems} />
            <Coin kind="diamond" label="Diamantes" value={profile.diamonds} />
          </div>
          {profile.team.length > 0 && (
            <ol className="team-strip" aria-label="Equipe">
              {profile.team.map((m) => (
                <li key={m.id} title={`${m.name ?? ""} nv ${m.level ?? "?"}`}
                  className={m.id === profile.active_pokemon_id ? "is-active" : undefined}>
                  <Sprite mon={m} atlas={atlas} looktypes={looktypes} size={40} />
                  <span className="num">{m.level ?? ""}</span>
                </li>
              ))}
            </ol>
          )}
          <div className="trainer-foot chips" title={`perfil de ${ago(profile.updated_at)}`}>
            <span className="chip"><strong>{num(profile.pokemon_count)}</strong> pokémons</span>
            <span className="chip"><strong>{num(profile.dex_caught)}</strong> na Pokédex</span>
            {profile.shiny_count > 0 && <span className="chip"><strong>{num(profile.shiny_count)}</strong> ✨</span>}
          </div>
        </>
      ) : (
        <p className="muted small">Perfil chegando…</p>
      )}
      {children}
    </section>
  );
}

export function Coin({ kind, label, value }: { kind: "gold" | "gem" | "diamond"; label: string; value: number | null }) {
  return (
    <div className={`coin coin-${kind}`}>
      <span className="coin-mark" aria-hidden />
      <span className="coin-value num">{num(value, { compact: true })}</span>
      <span className="coin-label">{label}</span>
    </div>
  );
}
