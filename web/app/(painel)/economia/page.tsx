import { Suspense } from "react";
import { EconomyView } from "./View";

/** Estática: os dados vêm no navegador, com cache (lib/query). O Suspense é do useSearchParams. */
export default function EconomyPage() {
  return <Suspense><EconomyView /></Suspense>;
}
