"use client";

import { usePathname } from "next/navigation";
import { navLabel } from "./nav";

/** O título da página já aparece no esqueleto (só os dados carregam). */
export function LoadingTitle() {
  const path = usePathname() ?? "/";
  return <h1>{navLabel(path) || "Carregando"}</h1>;
}
