"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Children, useState } from "react";

/**
 * Abas dentro da página (ex.: Resumo, Equipe, Estratégia, Ajustes da conta). Todas as abas vêm
 * renderizadas do servidor; trocar de aba só mostra outra, sem nova consulta. A aba fica na URL
 * (`?aba=`) para o link e o voltar funcionarem.
 */
export function SectionTabs({ tabs, children }: { tabs: { id: string; label: string }[]; children: React.ReactNode }) {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const initial = tabs.find((t) => t.id === params.get("aba"))?.id ?? tabs[0]?.id;
  const [current, setCurrent] = useState(initial);
  const panels = Children.toArray(children);

  const pick = (id: string) => {
    setCurrent(id);
    const q = new URLSearchParams(params.toString());
    if (id === tabs[0]?.id) q.delete("aba"); else q.set("aba", id);
    router.replace(`${path}${q.size ? `?${q}` : ""}`, { scroll: false });
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
