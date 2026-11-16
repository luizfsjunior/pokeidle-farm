import { Suspense } from "react";
import { PokedexView } from "./View";

/** Estática: os dados vêm no navegador, com cache (lib/query). O Suspense é do useSearchParams. */
export default function PokedexPage() {
  return <Suspense><PokedexView /></Suspense>;
}
