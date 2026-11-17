"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { Atlas } from "@/lib/sprites";
import type { Mon } from "@/lib/profile";

const POKEAPI = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/";
const NATIONAL_MAX = 1025;

/** Retrato de um pokémon, recortado do atlas do jogo. Sem atlas ou sem looktype, uma pokébola. */
export function Sprite({ mon, atlas, looktypes, size = 48 }: {
  mon: Mon | undefined;
  atlas: Atlas | null;
  looktypes?: Map<number, number>;
  size?: number;
}) {
  const lt = mon?.looktype ?? (mon?.species_id != null ? looktypes?.get(mon.species_id) : undefined);
  const slot = lt != null ? atlas?.slots[String(lt)] : undefined;
  const label = mon?.name ?? "Pokémon";
  if ((!slot || !atlas) && lt != null && atlas) {
    // fora do atlas do mapa: o retrato vem da folha de outfits do jogo (como o jogo faz)
    return <OutfitSprite lt={lt} size={size} label={label} fallback={<NationalSprite mon={mon} size={size} label={label} />} />;
  }
  if (!slot || !atlas) {
    // sem o atlas do jogo: o sprite da Pokédex nacional (PokeAPI), quando a espécie tem número nacional
    const sid = mon?.species_id;
    if (sid != null && sid >= 1 && sid <= NATIONAL_MAX) {
      return (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="sprite sprite-img" src={`${POKEAPI}${mon?.shiny ? "shiny/" : ""}${sid}.png`} alt={label}
          width={size} height={size} loading="lazy" decoding="async" />
      );
    }
    return <span className="sprite sprite-ball" role="img" aria-label={label} style={{ width: size, height: size }} />;
  }
  return (
    <span
      className="sprite"
      role="img"
      aria-label={label}
      style={{
        width: size,
        height: size,
        backgroundImage: `url('${atlas.image}')`,
        backgroundSize: `${atlas.cols * size}px ${atlas.rows * size}px`,
        backgroundPosition: `${-slot[0] * size}px ${-slot[1] * size}px`,
      }}
    />
  );
}

/** Sprite da Pokédex nacional (PokeAPI) quando a espécie tem número nacional; senão, uma pokébola. */
function NationalSprite({ mon, size, label }: { mon: Mon | undefined; size: number; label: string }) {
  const sid = mon?.species_id;
  if (sid != null && sid >= 1 && sid <= NATIONAL_MAX) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img className="sprite sprite-img" src={`${POKEAPI}${mon?.shiny ? "shiny/" : ""}${sid}.png`} alt={label}
        width={size} height={size} loading="lazy" decoding="async" />
    );
  }
  return <span className="sprite sprite-ball" role="img" aria-label={label} style={{ width: size, height: size }} />;
}

type Frame = { image: string; pw: number; ph: number; x: number; y: number; w: number; h: number } | null;

/** Recorte do quadro parado (direção 3, quadro 1) na folha WebP do outfit (/api/sprite). */
function OutfitSprite({ lt, size, label, fallback }: { lt: number; size: number; label: string; fallback: React.ReactNode }) {
  // só busca quando aparece na tela (a Pokédex tem mais de mil células)
  const ref = useRef<HTMLSpanElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { setSeen(true); io.disconnect(); } }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  const { data, isLoading } = useQuery<Frame>({
    enabled: seen,
    queryKey: ["outfit", lt],
    queryFn: async () => {
      const res = await fetch(`/api/sprite?lt=${lt}`);
      return res.ok ? ((await res.json()) as Frame) : null;
    },
    staleTime: 24 * 3600_000,
  });
  if (!seen || isLoading) return <span ref={ref} className="sprite sprite-ball" role="img" aria-label={label} style={{ width: size, height: size }} />;
  if (!data) return <>{fallback}</>;
  const k = Math.min(size / data.w, size / data.h);
  const w = data.w * k, h = data.h * k;
  return (
    <span className="sprite sprite-outfit" role="img" aria-label={label} style={{ width: size, height: size }}>
      <span style={{
        width: w, height: h,
        backgroundImage: `url('${data.image}')`,
        backgroundSize: `${data.pw * k}px ${data.ph * k}px`,
        backgroundPosition: `${-data.x * k}px ${-data.y * k}px`,
      }} />
    </span>
  );
}
