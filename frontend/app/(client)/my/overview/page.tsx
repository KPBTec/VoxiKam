"use client";
import { ErrorBanner } from '@/components/ErrorBanner'
import { useEffect, useState, useCallback } from "react";
import { apiGet } from "@/lib/api";
import { PhoneCall, Clock, DollarSign, Wallet } from "lucide-react";
import { CallsChart, ChartSeries } from "@/components/CallsChart";

function Stat({ label, value, icon: Icon, color, valueClassName = '' }:
  { label: string; value: string; icon: React.ElementType; color: string; valueClassName?: string }) {
  return (
    <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1">{label}</p>
          <p className={`text-2xl font-bold font-mono ${valueClassName}`}>{value}</p>
        </div>
        <div className={`p-2 rounded-lg ${color}`}><Icon size={18} /></div>
      </div>
    </div>
  );
}

const RANGES = [
  { label: "1h",  value: 1 },
  { label: "3h",  value: 3 },
  { label: "6h",  value: 6 },
  { label: "12h", value: 12 },
];

interface TimeseriesData { labels: string[]; series: ChartSeries[] }

export default function Overview() {
  const [data, setData] = useState<any>(null);
  const [ts,   setTs]   = useState<TimeseriesData | null>(null);
  const [range, setRange] = useState(1);
  const [error, setError] = useState("");

  const loadKpis = useCallback(() => apiGet("/my/today").then(d => { setData(d); setError(""); }).catch((e: any) => setError(e.message || "Error cargando el resumen")), []);
  const loadTs   = useCallback((r: number) => apiGet(`/timeseries/my?range=${r}`).then(setTs).catch(() => {}), []);

  useEffect(() => {
    loadKpis();
    const t = setInterval(loadKpis, 30000);
    return () => clearInterval(t);
  }, [loadKpis]);

  useEffect(() => {
    loadTs(range);
    const t = setInterval(() => loadTs(range), 60000);
    return () => clearInterval(t);
  }, [range, loadTs]);

  if (!data && error) return <div className="text-danger p-8">{error}</div>;
  if (!data) return <div className="text-[var(--color-muted)] p-8">Cargando...</div>;

  const fmt    = (n: any) => n ? `S/. ${parseFloat(n).toFixed(2)}` : "S/. 0.00";
  const fmtMin = (n: any) => n ? `${parseFloat(n).toFixed(0)} min` : "0 min";
  const sec2str = (s: number) => `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Mi resumen — Hoy</h1>
        <span className="text-xs text-[var(--color-muted)]">Actualiza cada 30s</span>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {data.billing_type === "prepago" && parseFloat(data.balance ?? 0) <= 0 && (
        <ErrorBanner>
          Sin saldo disponible — no podés iniciar llamadas nuevas hasta recargar. Las llamadas que ya estaban en curso no se cortan.
        </ErrorBanner>
      )}

      {data.show_kpis && (
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <Stat label="Llamadas hoy"   value={String(data.calls_today ?? 0)} icon={PhoneCall}  color="bg-brand-600/20 text-brand-400" />
          <Stat label="Minutos hoy"    value={fmtMin(data.minutes_today)}    icon={Clock}      color="bg-success/15 text-success" />
          <Stat label="Consumido hoy"  value={fmt(data.cost_today)}          icon={DollarSign} color="bg-warning/15 text-warning" />
          <Stat label="Disponible"     value={fmt(data.available)}           icon={Wallet}
            color={data.available <= 0 ? "bg-danger/15 text-danger" : "bg-success/15 text-success"}
            valueClassName={data.available <= 0 ? "text-danger" : "text-success"} />
        </div>
      )}

      {/* Timeseries — llamadas por minuto del cliente. No depende de overview_kpis
          (es el gráfico "Mis llamadas", un recurso propio) — siempre visible. */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h2 className="font-semibold text-sm">Mis llamadas</h2>
          <div className="flex gap-1">
            {RANGES.map(r => (
              <button key={r.value} onClick={() => setRange(r.value)}
                className={`px-3 py-1 rounded text-xs font-mono font-medium transition-colors ${
                  range === r.value
                    ? "bg-brand-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:text-white"
                }`}>
                {r.label}
              </button>
            ))}
          </div>
        </div>
        <CallsChart labels={ts?.labels ?? []} series={ts?.series ?? []} height={200} />
      </div>

      {/* Últimas llamadas */}
      {data.show_last_calls && (
        <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl">
          <div className="px-6 py-4 border-b border-[var(--color-border)]">
            <h2 className="font-semibold text-sm">Últimas 10 llamadas hoy</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                  <th className="px-6 py-3 text-left">Hora</th>
                  <th className="px-6 py-3 text-left">Destino</th>
                  <th className="px-6 py-3 text-right">Duración</th>
                  <th className="px-6 py-3 text-right">Costo</th>
                </tr>
              </thead>
              <tbody>
                {(data.last_calls ?? []).map((c: any, i: number) => (
                  <tr key={i} className="border-b border-[var(--color-border)]/50">
                    <td className="px-6 py-3 text-[var(--color-text-2)] text-xs">
                      {new Date(c.start_ts).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="px-6 py-3 font-mono text-xs">{c.dst_number}</td>
                    <td className="px-6 py-3 text-right font-mono text-xs">{sec2str(c.billsec)}</td>
                    <td className="px-6 py-3 text-right text-xs">S/. {parseFloat(c.sessionbill).toFixed(4)}</td>
                  </tr>
                ))}
                {!data.last_calls?.length && (
                  <tr><td colSpan={4} className="px-6 py-6 text-center text-[var(--color-muted)] text-sm">Sin llamadas hoy</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
