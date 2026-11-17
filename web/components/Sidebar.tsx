"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMe } from "@/lib/query/hooks";
import { clearCache } from "@/lib/query/provider";
import { Icon } from "./icons";
import { InstallApp } from "./InstallApp";
import { usePrefetch } from "./usePrefetch";
import { isActive, NAV_GROUPS } from "./nav";

/** Barra lateral do desktop: páginas em grupos, instalar e sair (docs/design/painel-ajustes.md). */
export function Sidebar() {
  const email = useMe().data ?? "";
  const path = usePathname() ?? "/";
  const warm = usePrefetch();
  return (
    <aside className="rail" aria-label="Navegação">
      <nav className="rail-nav">
        {NAV_GROUPS.map((g, i) => (
          <div key={i} className="rail-group">
            {g.title && <div className="rail-title rail-label">{g.title}</div>}
            {g.items.map((it) => (
              <Link key={it.href} href={it.href} className="rail-link" title={it.label} onMouseEnter={warm(it.href)} onFocus={warm(it.href)}
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
          <form action="/auth/sair" method="post" onSubmit={clearCache}>
            <button type="submit" className="rail-exit" title="Sair" aria-label="Sair"><Icon name="logout" size={18} /></button>
          </form>
        </div>
      </div>
    </aside>
  );
}
