import type { Metadata, Viewport } from "next";
import "@fontsource-variable/onest";
import "@fontsource/silkscreen/400.css";
import "@fontsource-variable/pixelify-sans";
import "./globals.css";

export const metadata: Metadata = {
  title: "pokeidle-farm",
  description: "Painel do farm: contas, métricas e objetivos.",
  robots: { index: false, follow: false },
  appleWebApp: { capable: true, title: "pokeidle", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0c0a1a",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
