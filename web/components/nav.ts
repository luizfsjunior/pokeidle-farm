/** As páginas do painel, em grupos (barra lateral) e as que vão na barra de baixo do celular. */
export type NavItem = { href: string; label: string; icon: string };

export const NAV_GROUPS: { title: string | null; items: NavItem[] }[] = [
  { title: null, items: [{ href: "/", label: "Contas", icon: "home" }] },
  {
    title: "Jogo",
    items: [
      { href: "/pokedex", label: "Pokédex", icon: "dex" },
      { href: "/hunts", label: "Hunts", icon: "map" },
      { href: "/objetivos", label: "Objetivos", icon: "target" },
      { href: "/metricas", label: "Métricas", icon: "chart" },
    ],
  },
  {
    title: "Economia",
    items: [
      { href: "/vendas", label: "Vendas", icon: "tag" },
      { href: "/mercado", label: "Mercado", icon: "coins" },
      { href: "/compensa", label: "Compensa?", icon: "scale" },
    ],
  },
  { title: "Sistema", items: [{ href: "/comandos", label: "Comandos", icon: "terminal" }] },
];

export const TAB_ITEMS = ["/", "/pokedex", "/vendas", "/hunts"];

export function isActive(path: string, href: string): boolean {
  return href === "/" ? path === "/" || path.startsWith("/contas") : path.startsWith(href);
}

export function navLabel(path: string): string {
  for (const g of NAV_GROUPS) for (const i of g.items) if (isActive(path, i.href)) return i.label;
  return "";
}
