import Link from "next/link";
import { Icon } from "./icons";

/** Cabeçalho da página: título, uma linha de contexto e ações à direita; filtros embaixo. */
export function PageHeader({ title, subtitle, actions, hint, children }: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  hint?: React.ReactNode; // explicação longa: fica num "ⓘ" ao lado do título
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="page-head-row">
        <div className="page-head-text">
          <div className="with-hint"><h1>{title}</h1>{hint && <Hint>{hint}</Hint>}</div>
          {subtitle && <p className="page-sub">{subtitle}</p>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
      {children && <div className="page-filters">{children}</div>}
    </header>
  );
}

/** Abas por link (conta, período...): a escolhida fica marcada, as outras navegam. */
export function LinkTabs({ label, items }: {
  label: string;
  items: { href: string; label: React.ReactNode; active: boolean; key?: string }[];
}) {
  return (
    <nav className="tabs" aria-label={label}>
      {items.map((it, i) => (
        <Link key={it.key ?? i} href={it.href} aria-current={it.active ? "true" : undefined} className="tab" scroll={false}>
          {it.label}
        </Link>
      ))}
    </nav>
  );
}

/** "ⓘ" que abre a explicação num balão: o texto longo sai da página e fica a um toque. */
export function Hint({ children, label = "Como é calculado" }: { children: React.ReactNode; label?: string }) {
  return (
    <details className="hint">
      <summary aria-label={label} title={label}><Icon name="info" size={15} /></summary>
      <div className="hint-pop" role="note">{children}</div>
    </details>
  );
}

/** Barrinha horizontal para comparar um valor com o maior da lista (dentro de tabelas e cartões). */
export function Bar({ value, max, tone = "accent", label }: {
  value: number | null | undefined;
  max: number;
  tone?: "accent" | "gem" | "gold" | "good" | "critical" | "link";
  label?: React.ReactNode;
}) {
  const pct = max > 0 && value != null && value > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <span className="bar-cell">
      {label != null && <span className="bar-label">{label}</span>}
      <span className={`bar bar-${tone}`} aria-hidden><span style={{ width: `${pct}%` }} /></span>
    </span>
  );
}

/** Seção recolhida: o detalhe fica a um toque, a página mostra só o título e um resumo à direita. */
export function Fold({ title, meta, open = false, children, flush = false }: {
  title: React.ReactNode;
  meta?: React.ReactNode;
  open?: boolean;
  flush?: boolean; // corpo sem padding (tabelas de ponta a ponta)
  children: React.ReactNode;
}) {
  return (
    <details className="fold" open={open}>
      <summary className="fold-head">
        <span className="fold-title">{title}</span>
        {meta != null && <span className="small muted fold-meta">{meta}</span>}
        <span className="fold-chevron" aria-hidden />
      </summary>
      <div className={flush ? "panel-flush" : "fold-body"}>{children}</div>
    </details>
  );
}

/** Cartão com cabeçalho (título, meta à direita) e corpo. */
export function Panel({ title, meta, hint, children, className = "", flush = false, id }: {
  title?: React.ReactNode;
  meta?: React.ReactNode;
  hint?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  flush?: boolean; // corpo sem padding (tabelas de ponta a ponta)
  id?: string;
}) {
  return (
    <section className={`panel ${className}`} id={id}>
      {(title || meta) && (
        <div className="panel-head">
          {title && <div className="with-hint"><h2>{title}</h2>{hint && <Hint>{hint}</Hint>}</div>}
          {meta && <div className="panel-meta">{meta}</div>}
        </div>
      )}
      <div className={flush ? "panel-flush" : "panel-body"}>{children}</div>
    </section>
  );
}

/** Indicador: número grande e rótulo. */
export function Kpi({ label, value, note, tone }: { label: string; value: React.ReactNode; note?: React.ReactNode; tone?: string }) {
  return (
    <div className={`kpi ${tone ? `kpi-${tone}` : ""}`}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value num">{value}</span>
      {note && <span className="kpi-note">{note}</span>}
    </div>
  );
}

/** Número pequeno com rótulo (grades de 2 a 4 colunas dentro de cartões). */
export function Stat({ label, value }: { label: React.ReactNode; value: React.ReactNode }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export function ErrorNote({ message }: { message?: string | null }) {
  if (!message) return null;
  return <p className="alert" role="alert">Erro ao ler o Supabase: {message}</p>;
}
