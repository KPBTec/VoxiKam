"use client";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { ErrorBanner } from "@/components/ErrorBanner";

interface JailConfig { maxretry: string | null; findtime: string | null; bantime: string | null; banaction: string | null }

const PARAM_LABELS: Record<keyof JailConfig, string> = {
  maxretry: "Intentos antes de banear", findtime: "Ventana (seg)",
  bantime: "Duración del ban (seg)", banaction: "Acción de ban",
};

export default function Fail2banPage() {
  const [banned, setBanned]     = useState<Record<string, string[]>>({});
  const [config, setConfig]     = useState<Record<string, JailConfig>>({});
  const [loading, setLoading]   = useState(true);
  const [unbanning, setUnbanning] = useState<string | null>(null);
  const [error, setError]       = useState("");

  async function load() {
    setLoading(true); setError("");
    try {
      const [b, c] = await Promise.all([
        apiGet("/admin/firewall/fail2ban"),
        apiGet("/admin/firewall/fail2ban/config"),
      ]);
      setBanned(b); setConfig(c);
    } catch (e: any) { setError(e.message || "Error cargando fail2ban"); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function unban(jail: string, ip: string) {
    setUnbanning(`${jail}:${ip}`);
    try {
      await apiPost("/admin/firewall/fail2ban/unban", { jail, ip });
      await load();
    } catch (e: any) {
      setError(e.message || "Error al desbanear la IP");
    } finally { setUnbanning(null); }
  }

  const card = "bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Fail2ban</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Baneos automáticos por intentos fallidos de login o SSH — separado de las reglas
          globales de <a href="/firewall" className="underline">Firewall</a>. No cuenta el
          rate-limit normal, solo rechazos de autenticación.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {/* Config actual por jail — solo lectura, viene de fail2ban-client get
          (lo que el proceso tiene REALMENTE cargado, no el archivo .conf —
          si alguien editó el archivo sin recargar fail2ban, el archivo
          mentiría; esto no). */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(config).map(([jail, cfg]) => (
          <div key={jail} className={`${card} p-5`}>
            <h2 className="font-semibold text-sm mb-3">{jail}</h2>
            <dl className="space-y-1.5">
              {(Object.keys(PARAM_LABELS) as (keyof JailConfig)[]).map(k => (
                <div key={k} className="flex items-center justify-between text-xs">
                  <dt className="text-[var(--color-text-2)]">{PARAM_LABELS[k]}</dt>
                  <dd className="font-mono text-[var(--color-text)]">{cfg?.[k] ?? '—'}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>

      <div className={`${card} overflow-x-auto`}>
        <div className="px-6 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-sm">IPs baneadas ahora</h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
              <th className="px-6 py-3 text-left">Jail</th>
              <th className="px-6 py-3 text-left">IP baneada</th>
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={3} className="px-6 py-8 text-center text-[var(--color-muted)] text-sm">Cargando...</td></tr>
            ) : Object.values(banned).every(ips => ips.length === 0) ? (
              <tr><td colSpan={3} className="px-6 py-8 text-center text-[var(--color-muted)] text-sm">Sin IPs baneadas</td></tr>
            ) : (
              Object.entries(banned).flatMap(([jail, ips]) =>
                ips.map(ip => (
                  <tr key={`${jail}:${ip}`} className="border-b border-[var(--color-border)]/50 hover:bg-white/2">
                    <td className="px-6 py-3 font-mono text-xs text-[var(--color-text-2)]">{jail}</td>
                    <td className="px-6 py-3 font-mono">{ip}</td>
                    <td className="px-6 py-3 text-right">
                      <button
                        disabled={unbanning === `${jail}:${ip}`}
                        onClick={() => unban(jail, ip)}
                        className="text-xs text-[var(--color-muted)] hover:text-brand-400 transition-colors disabled:opacity-50"
                      >
                        {unbanning === `${jail}:${ip}` ? "Desbaneando..." : "Desbanear"}
                      </button>
                    </td>
                  </tr>
                ))
              )
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
