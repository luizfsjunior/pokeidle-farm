import type { MetadataRoute } from "next";

/** Instalável como app no celular (docs/design/painel-fase-4.md). */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "pokeidle-farm",
    short_name: "pokeidle",
    description: "Painel das contas de farm do pokeidle.io",
    start_url: "/",
    display: "standalone",
    background_color: "#120f24",
    theme_color: "#0c0a1a",
    lang: "pt-BR",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
