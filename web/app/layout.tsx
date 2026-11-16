import type { Metadata, Viewport } from "next";
import "@fontsource-variable/onest";
import "@fontsource/silkscreen/400.css";
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
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfdfd" },
    { media: "(prefers-color-scheme: dark)", color: "#182026" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
