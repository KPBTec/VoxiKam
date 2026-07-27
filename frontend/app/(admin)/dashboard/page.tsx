"use client";
import { useEffect, useState, useCallback } from "react";
import { apiGet } from "@/lib/api";
import { PhoneCall, TrendingUp, DollarSign, Activity } from "lucide-react";
import { CallsChart, ChartSeries } from "@/components/CallsChart";
import { Gauge } from "@/components/Gauge";
import { groupByCustomer } from "@/lib/liveGrouping";
import { ErrorBanner } from "@/components/ErrorBanner";
import { LiveIndicator } from "@/components/LiveIndicator";

function KpiCard({ label, value, sub, icon: Icon, color }:
  { label: string; value: string; sub?: string; icon: React.ElementType; color: string }) {
  return (
    <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-[var(--color-text-2)] uppercase tracking-wider mb-1">{label}</p>
          <p className="text-2xl font-bold text-[var(--color-text)]">{value}</p>
          {sub && <p className="text-xs text-[var(--color-muted)] mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}><Icon size={20} /></div>
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

interface TsData {
  labels:      string[];
  by_customer: ChartSeries[];
  by_carrier:  ChartSeries[];
}

export default function Dashboard() {
  const [data,  setData]  = useState<any>(null);
  const [live,  setLive]  = useState<any>(null);
  const [ts,    setTs]    = useState<TsData | null>(null);
  const [sys,   setSys]   = useState<any>(null);
  const [range, setRange] = useState(1);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const loadTs = useCallback(async (r: number) => {
    try {
      const res = await apiGet(`/timeseries/admin?range=${r}`);
      setTs(res); setError("");
    } catch (e: any) { setError(e.message || "Error cargando el gráfico"); }
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const [d, l, s] = await Promise.all([
        apiGet("/admin/reports/dashboard"),
        apiGet("/admin/live"),
        apiGet("/admin/system"),
      ]);
      setData(d); setLive(l); setSys(s); setError("");
    } catch (e: any) { setError(e.message || "Error actualizando el dashboard"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    loadAll();
    const t = setInterval(loadAll, 30000);
    return () => clearInterval(t);
  }, [loadAll]);

  useEffect(() => {
    loadTs(range);
    const t = setInterval(() => loadTs(range), 60000);
    return () => clearInterval(t);
  }, [range, loadTs]);

  const fmt  = (n: number | null) => n ? `S/. ${n.toFixed(2)}` : "S/. 0.00";
  const fmtN = (n: number | null) => (n ?? 0).toLocaleString();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <LiveIndicator label="Auto-actualiza cada 30s" className="text-xs text-[var(--color-muted)]" />
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {/* Sistema — CPU | RAM | Disco | Red  (siempre arriba de todo) */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6">
        <div className="flex flex-wrap items-center gap-x-10 gap-y-6">
          <Gauge value={sys?.cpu_percent ?? 0} max={100} label="CPU" unit="%" size={128} />
          <Gauge
            value={sys?.ram_percent ?? 0} max={100} label="RAM" unit="%"
            sub={sys ? `${sys.ram_used_gb} / ${sys.ram_total_gb} GB` : undefined}
            size={128}
          />
          <Gauge
            value={sys?.disk_percent ?? 0} max={100} label="DISCO" unit="%"
            sub={sys ? `${sys.disk_used_gb} / ${sys.disk_total_gb} GB` : undefined}
            size={128}
          />

          {/* Red — interfaces, en tabla compacta en vez de columnas apiladas */}
          <div className="flex-1 min-w-[220px] pl-8 border-l border-[var(--color-border)] self-stretch flex flex-col justify-center">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-medium mb-3">Red — acumulado desde boot</p>
            {(sys?.net ?? []).length > 0 ? (
              <table className="text-xs w-full">
                <tbody>
                  {(sys?.net ?? []).map((n: any) => (
                    <tr key={n.iface}>
                      <td className="font-mono text-zinc-300 py-1 pr-4">{n.iface}</td>
                      <td className="py-1 pr-4 text-right">
                        <span className="text-zinc-500">↓ </span>
                        <span className="text-green-400 font-mono">{n.rx_str}</span>
                      </td>
                      <td className="py-1 text-right">
                        <span className="text-zinc-500">↑ </span>
                        <span className="text-brand-400 font-mono">{n.tx_str}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <span className="text-xs text-zinc-600">—</span>
            )}
          </div>
        </div>
      </div>

      {live && live?.kamailio?.available === false && (
        <div className="bg-yellow-950/40 border border-yellow-800/50 rounded-xl px-5 py-3 text-sm text-yellow-300">
          ⚠ El snapshot de llamadas activas de Kamailio no se actualiza — "Activas ahora" no es confiable ahora mismo. Ver detalle en <a href="/live" className="underline">Live</a>.
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard label="Activas ahora"    value={loading ? "···" : fmtN(live?.total)}            icon={Activity}    color="bg-brand-600/20 text-brand-400" />
        <KpiCard label="Llamadas hoy"     value={loading ? "···" : fmtN(data?.calls_today)}      icon={PhoneCall}   color="bg-success/15 text-success" />
        <KpiCard label="Facturado hoy"    value={loading ? "···" : fmt(data?.sessionbill_today)} icon={DollarSign}  color="bg-warning/15 text-warning" />
        <KpiCard label="Ganancia hoy"     value={loading ? "···" : fmt(data?.lucro_today)}       icon={TrendingUp}  color="bg-purple-900/30 text-purple-400" />
      </div>

      {/* Panel de timeseries */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">

        {/* Controles */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-semibold text-sm">Llamadas por minuto</h2>
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

        {/* Dos charts lado a lado */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <div>
            <p className="text-xs font-medium text-zinc-400 mb-2 uppercase tracking-wider">Por Carrier</p>
            <CallsChart
              labels={ts?.labels ?? []}
              series={ts?.by_carrier ?? []}
              height={200}
            />
          </div>
          <div>
            <p className="text-xs font-medium text-zinc-400 mb-2 uppercase tracking-wider">Por Cliente</p>
            <CallsChart
              labels={ts?.labels ?? []}
              series={ts?.by_customer ?? []}
              height={200}
            />
          </div>
        </div>

      </div>

      {/* Resumen compacto por cliente — el detalle completo (contestadas/timbrando)
          ya vive en Live; acá solo un vistazo rápido, no una tabla duplicada */}
      {(() => {
        const activeClients = groupByCustomer(live?.by_customer ?? []).filter((r: any) => r.active_calls > 0);
        if (!activeClients.length) return null;
        return (
          <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl px-5 py-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <LiveIndicator
                  label={`${activeClients.length} ${activeClients.length === 1 ? "cliente" : "clientes"} con llamadas activas`}
                  className="text-sm text-[var(--color-text-2)]"
                />
              </div>
              <a href="/live" className="text-xs text-brand-400 hover:text-brand-300">Ver detalle en Live →</a>
            </div>
            <div className="flex flex-wrap gap-2">
              {activeClients.map((r: any) => (
                <span key={r.customer_id ?? r.customer_name}
                  className="flex items-center gap-1.5 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-full pl-3 pr-2 py-1 text-xs">
                  <span className="text-[var(--color-text-2)]">{r.customer_name}</span>
                  <span className="bg-brand-600/20 text-brand-400 px-1.5 py-0.5 rounded-full font-mono">{r.active_calls}</span>
                </span>
              ))}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
