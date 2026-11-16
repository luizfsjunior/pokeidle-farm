import type { Metadata } from "next";
import "@fontsource-variable/onest";
import "@fontsource/silkscreen/400.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "pokeidle-farm",
  description: "Painel do farm: contas, métricas e objetivos.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
