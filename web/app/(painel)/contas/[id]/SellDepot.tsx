"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import type { CollectionMon } from "@/lib/collection";
import { num } from "@/lib/format";
import { useCommand } from "@/lib/useCommand";

/**
 * Vender o Depot (shop.sellAllPokemons): vende tudo que não está na equipe nem na Coleção. Pede
 * confirmação e manda quantos mostrou; o worker recusa se o Depot cresceu ou se tem shiny.
 */
export function SellDepot({ accountId, depot }: { accountId: string; depot: CollectionMon[] }) {
  const { send, cmd, error, busy } = useCommand();
  const [asking, setAsking] = useState(false);
  const shinies = depot.filter((m) => m.shiny).length;
  const n = depot.length;

  return (
    <div className="sell-depot">
      {!asking ? (
        <button type="button" className="ghost small" disabled={busy || n === 0} onClick={() => setAsking(true)}>
          Vender o Depot ({num(n)})
        </button>
      ) : (
        <>
          <span className="small">
            Vender {num(n)} {n === 1 ? "pokémon" : "pokémons"} do Depot por ouro? Não tem como desfazer.
          </span>
          {shinies > 0 && (
            <span className="small sell-warn">
              {shinies} shiny no Depot: guarde na Coleção antes (o worker recusa a venda com shiny).
            </span>
          )}
          <button type="button" className="danger small" disabled={busy || shinies > 0}
            onClick={() => { setAsking(false); void send(accountId, "depot.sell", { expected: n }); }}>
            Vender {num(n)}
          </button>
          <button type="button" className="ghost small" onClick={() => setAsking(false)}>Cancelar</button>
        </>
      )}
      <CommandStatus cmd={cmd} error={error} inline />
    </div>
  );
}
