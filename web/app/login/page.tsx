"use client";

import { useActionState } from "react";
import { login } from "./actions";

export default function LoginPage() {
  const [error, action, pending] = useActionState(login, null);
  return (
    <main style={{ maxWidth: 380, paddingTop: "12vh" }}>
      <div className="card stack">
        <h1 style={{ margin: 0 }}>pokeidle-farm</h1>
        <p className="secondary small" style={{ margin: 0 }}>Entre com o usuário do Supabase Auth.</p>
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
