"use client";

import { useActionState, useEffect } from "react";
import { clearCache } from "@/lib/query/provider";
import { login } from "./actions";

export default function LoginPage() {
  const [error, action, pending] = useActionState(login, null);
  useEffect(clearCache, []); // o cache do painel é de quem estava logado antes
  return (
    <main className="login">
      <div className="login-card stack">
        <div className="login-brand"><span className="rail-logo" aria-hidden /> <span>pokeidle-farm</span></div>
        <div>
          <h1>Entrar</h1>
          <p className="secondary small" style={{ margin: ".3rem 0 0" }}>Use o usuário do Supabase Auth.</p>
        </div>
        <form action={action} className="stack">
          <label>E-mail<input name="email" type="email" autoComplete="username" required /></label>
          <label>Senha<input name="password" type="password" autoComplete="current-password" required /></label>
          {error && <p className="error" role="alert">{error}</p>}
          <button type="submit" disabled={pending}>{pending ? "Entrando…" : "Entrar"}</button>
        </form>
      </div>
    </main>
  );
}
