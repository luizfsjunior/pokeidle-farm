import Link from "next/link";
import { MobileNav } from "./MobileNav";
import { Sidebar } from "./Sidebar";

/**
 * Casca do app: barra lateral (desktop) e barra de baixo (celular) paradas; a barra de cima, só com o
 * nome do app, rola junto com o conteúdo. A casca tem a altura da tela e só a área de conteúdo rola,
 * então nada depende da barra de endereço do navegador (docs/design/painel-ajustes.md).
 */
export function AppShell({ email, children }: { email: string; children: React.ReactNode }) {
  return (
    <div className="app">
      <div className="app-body">
        <Sidebar email={email} />
        <div className="app-scroll" id="conteudo">
          <header className="topbar">
            <Link href="/" className="topbar-brand"><span className="app-logo" aria-hidden />pokeidle-farm</Link>
          </header>
          <main className="content">{children}</main>
        </div>
      </div>
      <MobileNav email={email} />
    </div>
  );
}

/** As páginas ainda embrulham o conteúdo em <Shell>; a casca de verdade está no layout de (painel). */
export function Shell({ children }: { email?: string; children: React.ReactNode }) {
  return <>{children}</>;
}
