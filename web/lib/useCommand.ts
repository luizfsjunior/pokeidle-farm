"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { FINAL_STATUSES, type Command, type CommandType } from "@/lib/types";

const POLL_MS = 1500;
const GIVE_UP_MS = 6 * 60_000; // um pouco além do expires_at (5 min)

/** Cria um comando e acompanha o status até terminar. */
export function useCommand() {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const [cmd, setCmd] = useState<Command | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const send = useCallback(
    async (accountId: string, type: CommandType, params: Record<string, unknown> = {}) => {
      setError(null);
      const { data, error } = await supabase
        .from("commands").insert({ account_id: accountId, type, params }).select("*").single<Command>();
      if (error || !data) { setError(error?.message ?? "não foi possível enviar"); return; }
      setCmd(data);
      const started = Date.now();
      const poll = async () => {
        const { data: row } = await supabase.from("commands").select("*").eq("id", data.id).single<Command>();
        if (row) setCmd(row);
        if (row && FINAL_STATUSES.includes(row.status)) { router.refresh(); return; }
        if (Date.now() - started > GIVE_UP_MS) return;
        timer.current = setTimeout(poll, POLL_MS);
      };
      timer.current = setTimeout(poll, POLL_MS);
    },
    [supabase, router],
  );

  const busy = cmd !== null && !FINAL_STATUSES.includes(cmd.status);
  return { send, cmd, error, busy };
}
