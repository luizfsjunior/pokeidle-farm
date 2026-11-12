"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/supabase/server";
import { IV_STATS, type CaptureFilter } from "@/lib/types";

function numOrUndef(v: FormDataEntryValue | null): number | undefined {
  const s = String(v ?? "").trim().replace(",", ".");
  if (!s) return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

export async function createGoal(_prev: string | null, form: FormData): Promise<string | null> {
  const { supabase, userId } = await requireUser();
  const kind = String(form.get("kind")) as "metric" | "capture";
  const name = String(form.get("name") ?? "").trim();
  const target = numOrUndef(form.get("target"));
  if (!name) return "Dê um nome ao objetivo.";
  if (!target || target <= 0) return "A meta precisa ser maior que zero.";

  const deadlineRaw = String(form.get("deadline") ?? "");
  // datetime-local chega sem fuso: interpreta como horário de Brasília (UTC-3, sem horário de verão).
  const deadline = deadlineRaw ? new Date(`${deadlineRaw}:00-03:00`).toISOString() : null;
  if (deadline && new Date(deadline) <= new Date()) return "O prazo precisa estar no futuro.";

  let filter: CaptureFilter = {};
  let metric: string | null = null;
  if (kind === "metric") {
    metric = String(form.get("metric") ?? "");
    if (!metric) return "Escolha a métrica.";
  } else {
    const species = String(form.get("species") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    const shiny = String(form.get("shiny") ?? "");
    const minIvs: Record<string, number> = {};
    for (const st of IV_STATS) {
      const v = numOrUndef(form.get(`iv_${st}`));
      if (v !== undefined) minIvs[st] = v;
    }
    filter = {
      ...(species.length ? { species } : {}),
      ...(numOrUndef(form.get("min_quality")) !== undefined ? { min_quality: numOrUndef(form.get("min_quality")) } : {}),
      ...(numOrUndef(form.get("min_potency")) !== undefined ? { min_potency: numOrUndef(form.get("min_potency")) } : {}),
      ...(shiny ? { shiny: shiny === "true" } : {}),
      ...(numOrUndef(form.get("min_iv_sum")) !== undefined ? { min_iv_sum: numOrUndef(form.get("min_iv_sum")) } : {}),
      ...(Object.keys(minIvs).length ? { min_ivs: minIvs } : {}),
    };
  }

  const { data, error } = await supabase
    .from("goals")
    .insert({
      owner_id: userId,
      name,
      kind,
      metric,
      filter,
      target,
      deadline,
      account_id: String(form.get("account_id") ?? "") || null,
      hunt_slug: String(form.get("hunt_slug") ?? "").trim() || null,
    })
    .select("id")
    .single();
  if (error) return error.message;
  revalidatePath("/objetivos");
  redirect(`/objetivos/${data.id}`);
}

export async function setGoalStatus(form: FormData) {
  const { supabase } = await requireUser();
  const id = String(form.get("id"));
  const status = String(form.get("status"));
  if (!["active", "archived"].includes(status)) return;
  await supabase.from("goals").update({ status }).eq("id", id);
  revalidatePath("/objetivos");
  revalidatePath(`/objetivos/${id}`);
}

export async function deleteGoal(form: FormData) {
  const { supabase } = await requireUser();
  await supabase.from("goals").delete().eq("id", String(form.get("id")));
  revalidatePath("/objetivos");
  redirect("/objetivos");
}
