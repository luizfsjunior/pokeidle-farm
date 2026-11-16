/** Enquanto a página carrega: o esqueleto aparece na hora do clique, com a casca parada. */
export default function Loading() {
  return (
    <div className="loading" aria-busy="true" aria-label="Carregando">
      <div className="skeleton" style={{ height: 34, width: 220 }} />
      <div className="skeleton" style={{ height: 18, width: "55%" }} />
      <div className="kpis">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 86 }} />)}</div>
      <div className="skeleton" style={{ height: 260 }} />
    </div>
  );
}
