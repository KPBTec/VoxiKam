"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiPost, getErrorMessage } from "@/lib/api";
import { Logo } from "@/components/Logo";

function ResetPasswordForm() {
  const router = useRouter();
  const token  = useSearchParams().get("token") ?? "";

  const [password, setPassword]   = useState("");
  const [confirm, setConfirm]     = useState("");
  const [loading, setLoading]     = useState(false);
  const [done, setDone]           = useState(false);
  const [error, setError]         = useState("");

  useEffect(() => { document.title = "Restablecer contraseña · VoxiKam"; }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) { setError("La contraseña debe tener al menos 8 caracteres"); return; }
    if (password !== confirm) { setError("Las contraseñas no coinciden"); return; }
    setLoading(true);
    try {
      await apiPost("/auth/reset-password", { token, new_password: password });
      setDone(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (e: unknown) {
      setError(getErrorMessage(e, "El link es inválido o ya venció"));
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
            Nueva contraseña
          </h1>
        </div>

        {!token && (
          <div className="text-sm rounded-lg px-4 py-3" style={{ background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.25)", color: "var(--color-danger)" }}>
            Falta el token del link — pedí uno nuevo desde <Link href="/forgot-password" className="underline">Recuperar contraseña</Link>.
          </div>
        )}

        {error && (
          <div className="text-sm rounded-lg px-4 py-3" style={{ background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.25)", color: "var(--color-danger)" }}>
            {error}
          </div>
        )}

        {done ? (
          <div className="text-sm rounded-lg px-4 py-3" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-success)" }}>
            Contraseña actualizada — te llevamos al login…
          </div>
        ) : token && (
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="rp-password" className="block text-[11px] font-semibold uppercase tracking-widest" style={{ color: "var(--color-text-2)" }}>
                Nueva contraseña
              </label>
              <input
                id="rp-password"
                type="password" required minLength={8} value={password}
                onChange={e => setPassword(e.target.value)}
                className="focus-ring w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all"
                style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", color: "var(--color-text)" }}
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="rp-confirm" className="block text-[11px] font-semibold uppercase tracking-widest" style={{ color: "var(--color-text-2)" }}>
                Confirmar contraseña
              </label>
              <input
                id="rp-confirm"
                type="password" required minLength={8} value={confirm}
                onChange={e => setConfirm(e.target.value)}
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
              {loading ? "Guardando..." : "Restablecer contraseña"}
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

export default function ResetPasswordPage() {
  // useSearchParams requiere un límite <Suspense> en App Router — sin esto,
  // `next build` falla con "should be wrapped in a suspense boundary".
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
