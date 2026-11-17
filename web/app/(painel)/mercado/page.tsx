import { Suspense } from "react";
import { MarketView } from "./View";

/** Estática: os dados vêm no navegador, com cache (lib/query). O Suspense é do useSearchParams. */
export default function MarketPage() {
  return <Suspense><MarketView /></Suspense>;
}
