"use client";

import { useSearchParams } from "next/navigation";
import { Children, useState } from "react";

/**
 * Abas dentro da página (ex.: Resumo, Equipe, Estratégia, Ajustes da conta). Todas as abas vêm
 * renderizadas do servidor; trocar de aba só mostra outra, sem nova consulta. A aba fica na URL
 * (`?aba=`, pelo history nativo) para o link funcionar.
 */
export function SectionTabs({ tabs, children }: { tabs: { id: string; label: string }[]; children: React.ReactNode }) {
  const params = useSearchParams();
  const initial = tabs.find((t) => t.id === params.get("aba"))?.id ?? tabs[0]?.id;
  const [current, setCurrent] = useState(initial);
  const panels = Children.toArray(children);

  const pick = (id: string) => {
    setCurrent(id);
    // só a URL muda (history nativo, sem ir ao servidor): a troca é instantânea
    const url = new URL(window.location.href);
    if (id === tabs[0]?.id) url.searchParams.delete("aba"); else url.searchParams.set("aba", id);
    window.history.replaceState(null, "", url);
  };

  return (
    <div className="section-tabs">
      <div className="tabs section-tabs-bar" role="tablist" aria-label="Seções">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={current === t.id}
            aria-controls={`panel-${t.id}`} className="tab" aria-current={current === t.id ? "true" : undefined}
            onClick={() => pick(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t, i) => (
        <div key={t.id} role="tabpanel" id={`panel-${t.id}`} aria-labelledby={`tab-${t.id}`} hidden={current !== t.id} className="stack">
          {panels[i]}
        </div>
      ))}
    </div>
  );
}
