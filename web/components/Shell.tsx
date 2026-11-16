import { MobileNav } from "./MobileNav";
import { Sidebar } from "./Sidebar";

/** Casca do app: barra lateral no desktop, barras de cima e de baixo no celular. */
export function Shell({ email, children }: { email: string; children: React.ReactNode }) {
  return (
    <div className="app">
      <Sidebar email={email} />
      <MobileNav email={email} />
      <main className="content">{children}</main>
    </div>
  );
}
