import { AppShell } from "@/components/Shell";
import { QueryProvider } from "@/lib/query/provider";

/**
 * A casca fica no layout: ao navegar, a barra lateral e as barras do celular continuam na tela e só o
 * conteúdo troca. O layout não lê cookie (o proxy.ts já barra quem não entrou), então as páginas são
 * estáticas: abrem na hora e buscam os dados no navegador, com cache (lib/query, docs/design/painel-swr.md).
 */
export default function PainelLayout({ children }: { children: React.ReactNode }) {
  return <QueryProvider><AppShell>{children}</AppShell></QueryProvider>;
}
