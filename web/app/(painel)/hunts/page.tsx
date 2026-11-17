import { Suspense } from "react";
import { HuntsView } from "./View";

/** Estática: os dados vêm no navegador, com cache (lib/query). O Suspense é do useSearchParams. */
export default function HuntsPage() {
  return <Suspense><HuntsView /></Suspense>;
}
