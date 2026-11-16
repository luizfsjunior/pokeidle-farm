import { num } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";
import { HudTitle } from "./HudTitle";

/**
 * Barra do topo no estilo HUD de fliperama: a página atual e, à direita, o placar das contas
 * (ouro, gemas, diamantes somados e quantas estão conectadas). No celular ela rola com a página.
 */
export async function Hud() {
  const supabase = await createClient();
  const [acc, prof] = await Promise.all([
    supabase.from("accounts").select("id, role, status"),
    supabase.from("account_profile").select("gold, gems, diamonds"),
  ]);
  const farm = (acc.data ?? []).filter((a) => a.role === "farm");
  const online = farm.filter((a) => a.status === "ready").length;
  const rows = (prof.data ?? []) as { gold: number | null; gems: number | null; diamonds: number | null }[];
  const sum = (k: "gold" | "gems" | "diamonds") => rows.reduce((s, r) => s + (Number(r[k]) || 0), 0);
  return (
    <header className="hud">
      <span className="hud-logo rail-logo" aria-hidden />
      <HudTitle />
      <div className="hud-score" aria-label="Placar das contas">
        <span className="hud-chip hud-gold" title="Ouro nas contas"><i aria-hidden />{num(sum("gold"), { compact: true })}</span>
        <span className="hud-chip hud-gem" title="Gemas nas contas"><i aria-hidden />{num(sum("gems"))}</span>
        <span className="hud-chip hud-diamond" title="Diamantes nas contas"><i aria-hidden />{num(sum("diamonds"))}</span>
        <span className={`hud-chip hud-online ${farm.length && online === farm.length ? "is-on" : ""}`} title="Contas conectadas">
          <i aria-hidden />{online}/{farm.length}
        </span>
      </div>
    </header>
  );
}
