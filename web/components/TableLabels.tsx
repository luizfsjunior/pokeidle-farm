"use client";

import { useEffect } from "react";

/**
 * No celular as tabelas viram cartões (CSS em globals.css, `table.rt`): cada célula precisa do nome da
 * coluna ao lado do valor. Em vez de repetir o rótulo em toda página, este observador copia o texto do
 * <th> para o `data-label` de cada <td> das tabelas do conteúdo. Tabela com `data-keep` fica como está.
 */
export function TableLabels() {
  useEffect(() => {
    const root = document.getElementById("conteudo");
    if (!root) return;
    let queued = false;
    const label = () => {
      queued = false;
      for (const table of root.querySelectorAll<HTMLTableElement>("main table:not([data-keep])")) {
        const heads = [...table.querySelectorAll("thead th")].map((th) => th.textContent?.trim() ?? "");
        if (heads.length === 0) continue;
        if (!table.classList.contains("rt")) table.classList.add("rt");
        for (const row of table.tBodies[0]?.rows ?? []) {
          [...row.cells].forEach((td, i) => {
            const text = heads[i] ?? "";
            if (td.dataset.label !== text) td.dataset.label = text;
          });
        }
      }
    };
    const obs = new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(label);
    });
    obs.observe(root, { childList: true, subtree: true });
    label();
    return () => obs.disconnect();
  }, []);
  return null;
}
