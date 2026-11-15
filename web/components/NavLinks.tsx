"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "Visão geral"],
  ["/hunts", "Hunts"],
  ["/metricas", "Métricas"],
  ["/objetivos", "Objetivos"],
  ["/mercado", "Mercado"],
  ["/compensa", "Compensa?"],
  ["/comandos", "Comandos"],
] as const;

/** Menu do topo com a página atual destacada (a página da conta conta como Visão geral). */
export function NavLinks() {
  const path = usePathname() ?? "/";
  const active = (href: string) => (href === "/" ? path === "/" || path.startsWith("/contas") : path.startsWith(href));
  return (
    <nav>
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
          style={active(href) ? { fontWeight: 600, textDecoration: "underline", textUnderlineOffset: "4px" } : undefined}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
