"use client";

import { useIsFetching } from "@tanstack/react-query";

/**
 * Carregamento só dos dados (docs/design/painel-swr.md): título, descrição, abas, cabeçalhos de tabela
 * e títulos de card aparecem na hora; no lugar de cada valor ainda sem dado, uma barrinha animada.
 */
export function Ld({ w = "4ch", h }: { w?: string | number; h?: string | number }) {
  return <span className="ld" style={{ width: w, height: h }} aria-hidden />;
}

/** Linhas de tabela carregando, com o cabeçalho real em cima. */
export function LdRows({ cols, rows = 4 }: { cols: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} aria-hidden>
          {Array.from({ length: cols }, (_, c) => (
            <td key={c}><Ld w={c === 0 ? "9ch" : "4ch"} /></td>
          ))}
        </tr>
      ))}
    </>
  );
}

/** Um bloco (gráfico, card de dado) carregando. */
export function LdBlock({ h = 160 }: { h?: number }) {
  return <div className="ld ld-block" style={{ height: h }} aria-hidden />;
}

/** Linha fina no topo enquanto alguma consulta está buscando (inclusive a atualização por baixo). */
export function FetchBar() {
  const n = useIsFetching();
  return <div className={`fetchbar ${n > 0 ? "is-on" : ""}`} role="progressbar" aria-hidden={n === 0} aria-label="Atualizando" />;
}
