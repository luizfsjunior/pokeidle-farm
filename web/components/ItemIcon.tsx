"use client";

import { useEffect, useRef, useState } from "react";

/** Ícone de item do jogo; se a imagem não existir, as iniciais do nome. */
export function ItemIcon({ src, name, size = 32 }: { src: string | null; name: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLImageElement>(null);
  // a imagem pode falhar antes da hidratação, quando o onError ainda não está ligado
  useEffect(() => {
    const img = ref.current;
    if (img && img.complete && img.naturalWidth === 0) setFailed(true);
  }, [src]);
  if (!src || failed) {
    const initials = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
    return (
      <span className="item-icon item-icon-empty" aria-hidden style={{ width: size, height: size }}>
        {initials}
      </span>
    );
  }
  return (
    <img ref={ref} className="item-icon" src={src} alt="" width={size} height={size} loading="lazy" onError={() => setFailed(true)} />
  );
}
