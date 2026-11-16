"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "./icons";
import { InstallApp } from "./InstallApp";
import { isActive, NAV_GROUPS, navLabel, TAB_ITEMS } from "./nav";

/**
 * Celular: barra do topo com a página atual (rola junto, sem pular) e barra fixa embaixo com as
 * 4 páginas mais usadas e "Mais" (gaveta com o resto, instalar e sair).
 */
export function MobileNav({ email }: { email: string }) {
  const path = usePathname() ?? "/";
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const all = NAV_GROUPS.flatMap((g) => g.items);
  const tabs = TAB_ITEMS.map((href) => all.find((i) => i.href === href)!);
  const rest = all.filter((i) => !TAB_ITEMS.includes(i.href));
  const restActive = rest.some((i) => isActive(path, i.href));

  return (
    <>
      <header className="mbar">
        <Link href="/" className="rail-logo" aria-label="Início" />
        <span className="mbar-title">{navLabel(path) || "pokeidle-farm"}</span>
      </header>

      {open && <div className="sheet-backdrop" onClick={() => setOpen(false)} aria-hidden />}
      <div className={`sheet ${open ? "is-open" : ""}`} role="dialog" aria-modal="true" aria-label="Mais páginas" hidden={!open}>
        <div className="sheet-grip" aria-hidden />
        <ul>
          {rest.map((i) => (
            <li key={i.href}>
              <Link href={i.href} aria-current={isActive(path, i.href) ? "page" : undefined}>
                <Icon name={i.icon} /> {i.label}
              </Link>
            </li>
          ))}
        </ul>
        <InstallApp />
        <div className="sheet-foot">
          <span className="muted small">{email}</span>
          <form action="/auth/sair" method="post"><button className="ghost small" type="submit">Sair</button></form>
        </div>
      </div>

      <nav className="tabbar" aria-label="Páginas">
        {tabs.map((i) => (
          <Link key={i.href} href={i.href} aria-current={isActive(path, i.href) ? "page" : undefined}>
            <Icon name={i.icon} size={22} />
            <span>{i.label}</span>
          </Link>
        ))}
        <button type="button" className={restActive || open ? "is-on" : undefined} aria-expanded={open}
          onClick={() => setOpen((o) => !o)}>
          <Icon name="more" size={22} />
          <span>Mais</span>
        </button>
      </nav>
    </>
  );
}
