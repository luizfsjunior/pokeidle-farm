import type { NextConfig } from "next";

// No Codespaces o navegador acessa por <codespace>-3000.app.github.dev, mas o
// servidor vê localhost: libera essa origem para as Server Actions (só lá).
const codespaceOrigin =
  process.env.CODESPACE_NAME && process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN
    ? [`${process.env.CODESPACE_NAME}-3000.${process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}`]
    : [];

const config: NextConfig = {
  poweredByHeader: false,
  // Vendas, Mercado e Compensa viraram a página Economia (docs/design/painel-ux-v2.md): os atalhos antigos
  // (e o app instalado) continuam abrindo
  async redirects() {
    return ["vendas", "mercado", "compensa"].map((p) => ({ source: `/${p}`, destination: "/economia", permanent: false }));
  },
  experimental: {
    serverActions: { allowedOrigins: codespaceOrigin },
    // stale-while-revalidate na navegação (docs/design/painel-swr.md): a página já visitada volta na
    // hora, do cache do navegador, e o <Revalidate> busca a versão nova por baixo e troca quando chega
    staleTimes: { dynamic: 600, static: 600 },
  },
};

export default config;
