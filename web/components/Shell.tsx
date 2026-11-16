import Link from "next/link";
import { MobileNav } from "./MobileNav";
import { NavLinks } from "./NavLinks";

export function Shell({ email, children }: { email: string; children: React.ReactNode }) {
  return (
    <>
      <header className="topbar">
        <Link href="/" className="brand">pokeidle-farm</Link>
        <NavLinks />
        <span className="muted small topbar-email">{email}</span>
        <form action="/auth/sair" method="post" className="topbar-exit">
          <button className="ghost" type="submit">Sair</button>
        </form>
      </header>
      <main>{children}</main>
      <MobileNav email={email} />
    </>
  );
}
