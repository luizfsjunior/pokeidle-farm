"use client";

import { useEffect, useState } from "react";
import { Icon } from "./icons";

type PromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

/**
 * "Instalar o app": no Chrome/Edge/Android usa o pedido de instalação do navegador; no iPhone o Safari
 * não tem esse pedido, então mostra o caminho (Compartilhar → Adicionar à Tela de Início). Some quando
 * o painel já está aberto como app.
 */
export function InstallApp({ compact = false }: { compact?: boolean }) {
  const [prompt, setPrompt] = useState<PromptEvent | null>(null);
  const [ios, setIos] = useState(false);
  const [installed, setInstalled] = useState(true);
  const [hint, setHint] = useState(false);

  useEffect(() => {
    const standalone = window.matchMedia("(display-mode: standalone)").matches
      || (navigator as Navigator & { standalone?: boolean }).standalone === true;
    setInstalled(standalone);
    setIos(/iphone|ipad|ipod/i.test(navigator.userAgent));
    const onPrompt = (e: Event) => { e.preventDefault(); setPrompt(e as PromptEvent); };
    const onInstalled = () => setInstalled(true);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (installed || (!prompt && !ios)) return null;
  return (
    <div className="install">
      <button
        type="button"
        className="install-btn"
        onClick={async () => {
          if (prompt) { await prompt.prompt(); setPrompt(null); } else setHint((h) => !h);
        }}
      >
        <Icon name="download" size={18} />
        <span className={compact ? "rail-label" : undefined}>Instalar o app</span>
      </button>
      {hint && ios && (
        <p className="install-hint">No Safari: toque em Compartilhar e depois em <strong>Adicionar à Tela de Início</strong>.</p>
      )}
    </div>
  );
}
