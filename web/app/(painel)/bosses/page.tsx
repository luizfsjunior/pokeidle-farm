import { Suspense } from "react";
import { BossesView } from "./View";

/** Estática: os dados vêm no navegador, com cache (lib/query). O Suspense é do useSearchParams. */
export default function BossesPage() {
  return <Suspense><BossesView /></Suspense>;
}
