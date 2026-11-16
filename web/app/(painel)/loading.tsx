import { LoadingTitle } from "@/components/LoadingTitle";

/**
 * Só na primeira visita a uma página (depois ela vem do cache e se atualiza por baixo): a casca e o
 * título ficam, e só os blocos de dados aparecem como esqueleto.
 */
export default function Loading() {
  return (
    <div aria-busy="true" aria-label="Carregando">
      <header className="page-head">
        <div className="page-head-row"><div className="page-head-text"><LoadingTitle /><div className="skeleton" style={{ height: 16, width: 320, maxWidth: "80%" }} /></div></div>
        <div className="page-filters"><div className="skeleton" style={{ height: 34, width: 260, maxWidth: "100%" }} /></div>
      </header>
      <div className="stack">
        <div className="kpis">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 84 }} />)}</div>
        <div className="skeleton" style={{ height: 280 }} />
      </div>
    </div>
  );
}
