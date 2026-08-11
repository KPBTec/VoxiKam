"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiPost } from "@/lib/api";
import { Logo } from "@/components/Logo";

export default function ForgotPasswordPage() {
  const [email, setEmail]     = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent]       = useState(false);
  const [error, setError]     = useState("");

  useEffect(() => { document.title = "Recuperar contraseña · VoxiKam"; }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      // El backend responde siempre {ok: true} exista o no el email — nunca
      // hay una rama de error real acá salvo un problema de conexión, a
      // propósito (no revela si una cuenta existe).
      await apiPost("/auth/forgot-password", { email });
      setSent(true);
    } catch {
      setError("Error de conexión — intentá de nuevo en un momento");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-4"
      style={{
        background: "var(--color-surface)",
        backgroundImage: "radial-gradient(ellipse 80% 50% at 50% -5%, rgba(221,139,61,.12) 0%, transparent 65%)",
      }}
    >
      <div className="mb-8">
        <Logo size="lg" />
      </div>

      <div
        className="riveted w-full max-w-sm p-8 space-y-5"
        style={{
          background: "var(--color-card)",
          border: "1px solid var(--color-border)",
          boxShadow: "0 8px 40px rgba(0,0,0,.5), 0 0 60px rgba(221,139,61,.06)",
        }}
      >
        <div>
          <h1 className="nameplate text-lg" style={{ color: "var(--color-text)" }}>
            Recuperar contraseña
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--color-text-2)" }}>
            Te mandamos un link para restablecerla
          </p>
        </div>

        {error && (
          <div className="text-sm rounded-lg px-4 py-3" style={{ background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.25)", color: "var(--color-danger)" }}>
            {error}
          </div>
        )}

        {sent ? (
          <div className="text-sm rounded-lg px-4 py-3" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-text)" }}>
            Si <strong>{email}</strong> tiene una cuenta acá, te llegó un correo con instrucciones. El link vence en 1 hora.
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="fp-email" className="block text-[11px] font-semibold uppercase tracking-widest" style={{ color: "var(--color-text-2)" }}>
                Email
              </label>
              <input
                id="fp-email"
                type="email" required value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="admin@empresa.com"
                className="focus-ring w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-text)" }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="focus-ring w-full rounded-lg py-2.5 text-sm font-semibold text-white transition-all mt-2 cursor-pointer"
              style={{
                background: loading ? "var(--color-brand-700)" : "var(--color-brand-600)",
                boxShadow: loading ? "none" : "0 0 24px rgba(221,139,61,.3)",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Enviando..." : "Enviar instrucciones"}
            </button>
          </form>
        )}

        <Link href="/login" className="focus-ring block text-center text-xs rounded-lg py-1" style={{ color: "var(--color-text-2)" }}>
          Volver a iniciar sesión
        </Link>
      </div>
    </div>
  );
}
