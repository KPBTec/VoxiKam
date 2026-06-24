"use client";
import { useEffect, useState, useCallback } from "react";
import { apiGet } from "@/lib/api";
import { PhoneCall, TrendingUp, DollarSign, Activity } from "lucide-react";
import { CallsChart, ChartSeries } from "@/components/CallsChart";
import { Gauge } from "@/components/Gauge";

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

  const loadTs = useCallback(async (r: number) => {
    const res = await apiGet(`/timeseries/admin?range=${r}`);
    setTs(res);
  }, []);

  const loadAll = useCallback(async () => {
    const [d, l, s] = await Promise.all([
      apiGet("/admin/reports/dashboard"),
      apiGet("/admin/live"),
      apiGet("/admin/system"),
    ]);
    setData(d); setLive(l); setSys(s);
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
        <span className="text-xs text-[var(--color-muted)]">Auto-actualiza cada 30s</span>
      </div>

      {/* Sistema — CPU | RAM | Red  (siempre arriba de todo) */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">
        <div className="grid grid-cols-3 gap-4 items-center">
          {/* CPU */}
          <div className="flex justify-center">
            <Gauge value={sys?.cpu_percent ?? 0} max={100} label="CPU" unit="%" size={130} />
          </div>
          {/* RAM */}
          <div className="flex justify-center">
            <Gauge
              value={sys?.ram_percent ?? 0} max={100} label="RAM" unit="%"
              sub={sys ? `${sys.ram_used_gb} / ${sys.ram_total_gb} GB` : undefined}
              size={130}
            />
          </div>
          {/* Red — interfaces */}
          <div className="flex flex-col gap-3 pl-4 border-l border-[var(--color-border)]">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-medium">Red</p>
            {(sys?.net ?? []).map((n: any) => (
              <div key={n.iface} className="flex flex-col gap-1">
                <span className="font-mono text-xs text-zinc-300">{n.iface}</span>
                <div className="flex gap-4">
                  <span className="text-xs text-zinc-500">↓ <span className="text-green-400 font-mono">{n.rx_str}</span></span>
                  <span className="text-xs text-zinc-500">↑ <span className="text-blue-400 font-mono">{n.tx_str}</span></span>
                </div>
              </div>
            ))}
            {!sys?.net?.length && <span className="text-xs text-zinc-600">—</span>}
            <p className="text-xs text-zinc-600">acumulado desde boot</p>
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard label="Activas ahora"    value={fmtN(live?.total)}            icon={Activity}    color="bg-brand-600/20 text-brand-400" />
        <KpiCard label="Llamadas hoy"     value={fmtN(data?.calls_today)}      icon={PhoneCall}   color="bg-green-900/30 text-green-400" />
        <KpiCard label="Facturado hoy"    value={fmt(data?.sessionbill_today)} icon={DollarSign}  color="bg-yellow-900/30 text-yellow-400" />
        <KpiCard label="Ganancia hoy"     value={fmt(data?.lucro_today)}       icon={TrendingUp}  color="bg-purple-900/30 text-purple-400" />
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

      {/* Tabla activas por cliente */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl">
        <div className="px-6 py-4 border-b border-[var(--color-border)] flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
          <h2 className="font-semibold text-sm">Llamadas activas por cliente</h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
              <th className="px-6 py-3 text-left">Cliente</th>
              <th className="px-6 py-3 text-right">Activas</th>
            </tr>
          </thead>
          <tbody>
            {(live?.by_customer ?? []).map((r: any) => (
              <tr key={r.customer_id} className="border-b border-[var(--color-border)]/50 hover:bg-white/2">
                <td className="px-6 py-3">{r.customer_name}</td>
                <td className="px-6 py-3 text-right">
                  <span className="bg-brand-600/20 text-brand-400 px-2 py-0.5 rounded-full text-xs font-mono">
                    {r.active_calls}
                  </span>
                </td>
              </tr>
            ))}
            {!live?.by_customer?.length && (
              <tr><td colSpan={2} className="px-6 py-8 text-center text-[var(--color-muted)] text-sm">Sin llamadas activas</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
