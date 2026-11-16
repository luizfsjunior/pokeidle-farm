import { Hud } from "./Hud";
import { MobileNav } from "./MobileNav";
import { Sidebar } from "./Sidebar";

/** Casca do app: barra lateral (desktop), HUD no topo, barra de baixo no celular. */
export function Shell({ email, children }: { email: string; children: React.ReactNode }) {
  return (
    <div className="app">
      <Sidebar email={email} />
      <div className="app-main">
        <Hud />
        <main className="content">{children}</main>
      </div>
      <MobileNav email={email} />
    </div>
  );
}
