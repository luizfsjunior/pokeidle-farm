import Link from "next/link";

export function Shell({ email, children }: { email: string; children: React.ReactNode }) {
  return (
    <>
      <header className="topbar">
        <Link href="/" className="brand">pokeidle-farm</Link>
        <nav>
          <Link href="/">Visão geral</Link>
          <Link href="/metricas">Métricas</Link>
          <Link href="/objetivos">Objetivos</Link>
          <Link href="/comandos">Comandos</Link>
        </nav>
        <span className="muted small">{email}</span>
        <form action="/auth/sair" method="post">
          <button className="ghost" type="submit">Sair</button>
        </form>
      </header>
      <main>{children}</main>
    </>
  );
}
