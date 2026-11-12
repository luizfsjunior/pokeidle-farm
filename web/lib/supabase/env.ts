export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";

// Trava de segurança: o painel só pode usar a chave pública.
if (SUPABASE_KEY.startsWith("sb_secret_")) {
  throw new Error(
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY recebeu uma chave secreta. Use a sb_publishable_ — a secreta é só do worker.",
  );
}
