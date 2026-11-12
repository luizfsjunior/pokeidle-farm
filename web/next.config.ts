import type { NextConfig } from "next";

// No Codespaces o navegador acessa por <codespace>-3000.app.github.dev, mas o
// servidor vê localhost: libera essa origem para as Server Actions (só lá).
const codespaceOrigin =
  process.env.CODESPACE_NAME && process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN
    ? [`${process.env.CODESPACE_NAME}-3000.${process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}`]
    : [];

const config: NextConfig = {
  poweredByHeader: false,
  experimental: {
    serverActions: { allowedOrigins: codespaceOrigin },
  },
};

export default config;
