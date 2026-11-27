/** As páginas do painel, em grupos (barra lateral) e as que vão na barra de baixo do celular. */
export type NavItem = { href: string; label: string; icon: string };

export const NAV_GROUPS: { title: string | null; items: NavItem[] }[] = [
  {
    title: null,
    items: [
      { href: "/", label: "Contas", icon: "home" },
      { href: "/historico", label: "Histórico", icon: "chart" },
    ],
  },
  {
    title: "Jogo",
    items: [
      { href: "/pokedex", label: "Pokédex", icon: "dex" },
      { href: "/hunts", label: "Hunts", icon: "map" },
      { href: "/bosses", label: "Bosses", icon: "crown" },
      { href: "/objetivos", label: "Objetivos", icon: "target" },
    ],
  },
  { title: null, items: [{ href: "/economia", label: "Economia", icon: "coins" }] },
  {
    title: "Sistema",
    items: [
      { href: "/metricas", label: "Métricas", icon: "chart" },
      { href: "/comandos", label: "Comandos", icon: "terminal" },
    ],
  },
];

/** Barra de baixo do celular: as 4 mais usadas; o resto fica em "Mais". */
export const TAB_ITEMS = ["/", "/pokedex", "/hunts", "/economia"];

export function isActive(path: string, href: string): boolean {
  return href === "/" ? path === "/" || path.startsWith("/contas") : path.startsWith(href);
}

export function navLabel(path: string): string {
  for (const g of NAV_GROUPS) for (const i of g.items) if (isActive(path, i.href)) return i.label;
  return "";
}
