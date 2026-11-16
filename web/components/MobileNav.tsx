"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/** Barra de baixo no celular: as 4 páginas mais usadas e "Mais" com o resto (docs/design/painel-fase-4.md). */
const MAIN = [
  ["/", "Contas", "home"],
  ["/pokedex", "Pokédex", "dex"],
  ["/vendas", "Vendas", "tag"],
  ["/hunts", "Hunts", "map"],
] as const;
const MORE = [
  ["/metricas", "Métricas"],
  ["/objetivos", "Objetivos"],
  ["/mercado", "Mercado"],
  ["/compensa", "Compensa?"],
  ["/comandos", "Comandos"],
] as const;

function Icon({ name }: { name: string }) {
  const common = { width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8,
    strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  switch (name) {
    case "home": return <svg {...common}><path d="M4 11l8-6 8 6v8a1 1 0 0 1-1 1h-4v-5H9v5H5a1 1 0 0 1-1-1z" /></svg>;
    case "dex": return <svg {...common}><rect x="5" y="3" width="14" height="18" rx="2" /><circle cx="12" cy="10" r="3" /><path d="M9 16h6" /></svg>;
    case "tag": return <svg {...common}><path d="M3 12V4h8l10 10-8 8z" /><circle cx="7.5" cy="8" r="1.3" /></svg>;
    case "map": return <svg {...common}><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></svg>;
    default: return <svg {...common}><circle cx="5" cy="12" r="1.4" /><circle cx="12" cy="12" r="1.4" /><circle cx="19" cy="12" r="1.4" /></svg>;
  }
}

export function MobileNav({ email }: { email: string }) {
  const path = usePathname() ?? "/";
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [path]);
  const active = (href: string) => (href === "/" ? path === "/" || path.startsWith("/contas") : path.startsWith(href));
  const moreActive = MORE.some(([href]) => active(href));

  return (
    <>
      {open && <button className="sheet-backdrop" aria-label="Fechar o menu" onClick={() => setOpen(false)} />}
      <div className={`sheet ${open ? "is-open" : ""}`} role="dialog" aria-label="Mais páginas" aria-hidden={!open}>
        <ul>
          {MORE.map(([href, label]) => (
            <li key={href}>
              <Link href={href} aria-current={active(href) ? "page" : undefined} tabIndex={open ? 0 : -1}>{label}</Link>
            </li>
          ))}
        </ul>
        <div className="sheet-foot">
          <span className="muted small">{email}</span>
          <form action="/auth/sair" method="post"><button className="ghost small" type="submit" tabIndex={open ? 0 : -1}>Sair</button></form>
        </div>
      </div>
      <nav className="tabbar" aria-label="Páginas">
        {MAIN.map(([href, label, icon]) => (
          <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}>
            <Icon name={icon} />
            <span>{label}</span>
          </Link>
        ))}
        <button type="button" className={moreActive || open ? "is-on" : undefined} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <Icon name="more" />
          <span>Mais</span>
        </button>
      </nav>
    </>
  );
}
