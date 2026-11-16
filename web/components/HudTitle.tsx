"use client";

import { usePathname } from "next/navigation";
import { navLabel } from "./nav";

export function HudTitle() {
  const path = usePathname() ?? "/";
  return <span className="hud-title">{navLabel(path) || "pokeidle-farm"}</span>;
}
