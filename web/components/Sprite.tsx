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
