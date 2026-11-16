"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./icons";
import { InstallApp } from "./InstallApp";
import { isActive, NAV_GROUPS } from "./nav";

/** Barra lateral do desktop: marca, páginas em grupos, instalar e sair (docs/design/painel-redesign.md). */
export function Sidebar({ email }: { email: string }) {
  const path = usePathname() ?? "/";
  return (
    <aside className="rail" aria-label="Navegação">
      <Link href="/" className="rail-brand" aria-label="pokeidle-farm, início">
        <span className="rail-logo" aria-hidden />
        <span className="rail-label">pokeidle-farm</span>
      </Link>
      <nav className="rail-nav">
        {NAV_GROUPS.map((g, i) => (
          <div key={i} className="rail-group">
            {g.title && <div className="rail-title rail-label">{g.title}</div>}
            {g.items.map((it) => (
              <Link key={it.href} href={it.href} className="rail-link" title={it.label}
                aria-current={isActive(path, it.href) ? "page" : undefined}>
                <Icon name={it.icon} />
                <span className="rail-label">{it.label}</span>
              </Link>
            ))}
          </div>
        ))}
      </nav>
      <div className="rail-foot">
        <InstallApp compact />
        <div className="rail-user">
          <span className="rail-avatar" aria-hidden>{email.slice(0, 1).toUpperCase()}</span>
          <span className="rail-email rail-label" title={email}>{email}</span>
          <form action="/auth/sair" method="post">
            <button type="submit" className="rail-exit" title="Sair" aria-label="Sair"><Icon name="logout" size={18} /></button>
          </form>
        </div>
      </div>
    </aside>
  );
}
