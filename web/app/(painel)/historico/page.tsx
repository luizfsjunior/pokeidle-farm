import { Suspense } from "react";
import { HistoryView } from "./View";

/** Estática: os dados vêm no navegador, com cache (lib/query). O Suspense é do useSearchParams. */
export default function HistoryPage() {
  return <Suspense><HistoryView /></Suspense>;
}
