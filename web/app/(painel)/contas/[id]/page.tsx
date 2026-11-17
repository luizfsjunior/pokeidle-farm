import { Suspense } from "react";
import { AccountView } from "./View";

/** Os dados vêm no navegador, com cache (lib/query). O Suspense é do useSearchParams das abas. */
export default function AccountPage() {
  return <Suspense><AccountView /></Suspense>;
}
