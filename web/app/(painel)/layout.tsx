import { AppShell } from "@/components/Shell";
import { requireUser } from "@/lib/supabase/server";

/**
 * A casca fica no layout: ao navegar, a barra lateral e as barras do celular continuam na tela e só o
 * conteúdo troca (com o esqueleto do loading.tsx enquanto o servidor responde).
 */
export default async function PainelLayout({ children }: { children: React.ReactNode }) {
  const { email } = await requireUser();
  return <AppShell email={email}>{children}</AppShell>;
}
