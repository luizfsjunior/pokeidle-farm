import { Suspense } from "react";
import { SalesView } from "./View";

/** Estática: os dados vêm no navegador, com cache (lib/query). O Suspense é do useSearchParams. */
export default function SalesPage() {
  return <Suspense><SalesView /></Suspense>;
}
