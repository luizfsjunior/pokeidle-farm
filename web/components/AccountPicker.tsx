"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { nickBadge } from "@/lib/format";

const KEY = "pf-conta"; // a última conta escolhida, para as outras páginas abrirem nela
const ALL = "todas";

function read(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}
function write(v: string) {
  try { localStorage.setItem(KEY, v); } catch { /* sem storage: só não lembra */ }
}

/**
 * Seletor de conta das páginas (Pokédex, Hunts, Bosses, Economia), no lugar das abas de conta que quebravam em
 * duas linhas no celular. A escolha fica na URL (`?conta=`) e é lembrada entre as páginas: abrir uma página sem
 * `?conta=` leva para a última conta escolhida.
 */
export function AccountPicker({ accounts, chosen, href, all = true, hasParam }: {
  accounts: { id: string; nick: string; role?: string }[];
  chosen: string | null; // null = todas
  href: (id: string | null) => string;
  all?: boolean;
  hasParam: boolean; // a URL já diz a conta: vale ela
}) {
  const router = useRouter();
  const ids = accounts.map((a) => a.id).join(",");

  useEffect(() => {
    if (hasParam || !ids) return;
    const stored = read();
    if (!stored) return;
    if (stored === ALL) {
      if (all && chosen != null) router.replace(href(null), { scroll: false });
    } else if (stored !== chosen && ids.split(",").includes(stored)) {
      router.replace(href(stored), { scroll: false });
    }
    // só na chegada à página
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasParam, ids]);

  return (
    <label className="acc-pick">
      <span className="tab-avatar" aria-hidden>
        {chosen ? nickBadge(accounts.find((a) => a.id === chosen)?.nick ?? "?") : "∑"}
      </span>
      <select value={chosen ?? ""} aria-label="Conta" onChange={(e) => {
        const v = e.target.value || null;
        write(v ?? ALL);
        router.replace(href(v), { scroll: false });
      }}>
        {all && <option value="">Todas as contas</option>}
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>{a.nick}{a.role === "personal" ? " (pessoal)" : ""}</option>
        ))}
      </select>
    </label>
  );
}
