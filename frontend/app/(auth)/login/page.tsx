"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { saveAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]     = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const form = new URLSearchParams({ username: email, password });
      const res = await apiFetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      });
      if (!res.ok) { setError("Credenciales incorrectas"); return; }
      const data = await res.json();
      saveAuth(data.access_token, {
        name: data.name, role: data.role, customer_id: data.customer_id,
        show_calls: data.show_calls, show_quality: data.show_quality,
        show_reports: data.show_reports, show_invoices: data.show_invoices,
        show_trunk_guide: data.show_trunk_guide,
      });
      router.push(data.role === "admin" ? "/dashboard" : "/my/overview");
    } catch {
      setError("Error de conexión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-surface)]">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-brand-500 text-4xl font-bold mb-2 tracking-tight">Kapla<span className="text-white">Billing</span></div>
          <p className="text-[var(--color-text-2)] text-sm">Plataforma SIP Class 4/5</p>
        </div>

        <form onSubmit={submit}
          className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-2xl p-8 space-y-5 shadow-xl">
          <h1 className="text-xl font-semibold text-[var(--color-text)]">Iniciar sesión</h1>

          {error && (
            <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div className="space-y-1">
            <label className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Email</label>
            <input
              type="email" required value={email} onChange={e => setEmail(e.target.value)}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg
                         px-4 py-3 text-[var(--color-text)] text-sm focus:outline-none
                         focus:border-brand-500 transition-colors"
              placeholder="admin@empresa.com"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Contraseña</label>
            <input
              type="password" required value={password} onChange={e => setPassword(e.target.value)}
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg
                         px-4 py-3 text-[var(--color-text)] text-sm focus:outline-none
                         focus:border-brand-500 transition-colors"
            />
          </div>

          <button type="submit" disabled={loading}
            className="w-full bg-brand-600 hover:bg-brand-500 disabled:opacity-50
                       text-white font-medium rounded-lg py-3 text-sm transition-colors">
            {loading ? "Ingresando..." : "Ingresar"}
          </button>
        </form>
      </div>
    </div>
  );
}
