"use server";

import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/supabase/server";

export async function cancelCommand(form: FormData) {
  const { supabase } = await requireUser();
  await supabase.rpc("cancel_command", { p_id: String(form.get("id")) });
  revalidatePath("/comandos");
}
