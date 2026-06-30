"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { saveAuth } from "@/lib/auth";
import { Logo } from "@/components/Logo";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

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
    <div
      className="min-h-screen flex flex-col items-center justify-center px-4"
      style={{
        background: "var(--color-surface)",
        backgroundImage: "radial-gradient(ellipse 80% 50% at 50% -5%, rgba(14,165,233,.12) 0%, transparent 65%)",
      }}
    >
      <div className="mb-8">
        <Logo size="lg" />
      </div>

      <div
        className="w-full max-w-sm rounded-2xl p-8 space-y-5"
        style={{
          background: "var(--color-card)",
          border: "1px solid var(--color-border)",
          boxShadow: "0 8px 40px rgba(0,0,0,.5), 0 0 60px rgba(14,165,233,.06)",
        }}
      >
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--color-text)" }}>
            Iniciar sesión
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--color-text-2)" }}>
            Ingresa tus credenciales para continuar
          </p>
        </div>

        {error && (
          <div
            className="text-sm rounded-lg px-4 py-3"
            style={{
              background: "rgba(239,68,68,.1)",
              border: "1px solid rgba(239,68,68,.25)",
              color: "var(--color-danger)",
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <label
              className="block text-[11px] font-semibold uppercase tracking-widest"
              style={{ color: "var(--color-text-2)" }}
            >
              Email
            </label>
            <input
              type="email" required value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="admin@empresa.com"
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all"
              style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                color: "var(--color-text)",
              }}
              onFocus={e => (e.currentTarget.style.borderColor = "var(--color-brand-500)")}
              onBlur={e  => (e.currentTarget.style.borderColor = "var(--color-border)")}
            />
          </div>

          <div className="space-y-1.5">
            <label
              className="block text-[11px] font-semibold uppercase tracking-widest"
              style={{ color: "var(--color-text-2)" }}
            >
              Contraseña
            </label>
            <input
              type="password" required value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all"
              style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                color: "var(--color-text)",
              }}
              onFocus={e => (e.currentTarget.style.borderColor = "var(--color-brand-500)")}
              onBlur={e  => (e.currentTarget.style.borderColor = "var(--color-border)")}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg py-2.5 text-sm font-semibold text-white transition-all mt-2 cursor-pointer"
            style={{
              background: loading ? "var(--color-brand-700)" : "var(--color-brand-600)",
              boxShadow: loading ? "none" : "0 0 24px rgba(14,165,233,.3)",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Ingresando..." : "Ingresar"}
          </button>
        </form>
      </div>

      <p className="mt-6 text-[11px]" style={{ color: "var(--color-muted)", opacity: 0.55 }}>
        KPBTec · Knowledge, Protection &amp; Business Technology
      </p>
    </div>
  );
}
