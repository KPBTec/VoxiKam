"use client";
import { useEffect, useState, useCallback } from "react";
import { apiGet, apiPost, apiPut } from "@/lib/api";
import { ChevronDown, ChevronRight, Terminal, Power, PowerOff } from "lucide-react";
import { StatusBadge, type BadgeVariant } from "@/components/StatusBadge";
import { ErrorBanner } from "@/components/ErrorBanner";

interface ServiceInfo {
  key: string;
  unit: string;
  label: string;
  load_state: string;
  active_state: string;
  sub_state: string;
  since: string | null;
  pid: string | null;
  restarts: string | null;
  recent_logs: string[];
}

interface OtherService {
  unit: string;
  running: boolean;
  reason?: string;
}

interface CronJob {
  key: string;
  label: string;
  status: "ok" | "stale" | "error" | "missing";
  last_run: string | null;
  age_seconds: number | null;
  last_line: string | null;
}

const CRON_STATUS_LABEL: Record<CronJob["status"], string> = {
  ok:      "al día",
  stale:   "atrasado",
  error:   "error",
  missing: "sin logs",
};

function cronStatusVariant(status: CronJob["status"]): BadgeVariant {
  switch (status) {
    case "ok":      return "success";
    case "stale":   return "warning";
    case "error":   return "danger";
    case "missing": return "muted";
  }
}
function cronDotCls(status: CronJob["status"]): string {
  switch (status) {
    case "ok":      return "bg-success";
    case "stale":   return "bg-warning";
    case "error":   return "bg-danger";
    case "missing": return "bg-[var(--color-muted)]";
  }
}
function cronTextCls(status: CronJob["status"]): string {
  switch (status) {
    case "ok":      return "text-success";
    case "stale":   return "text-warning";
    case "error":   return "text-danger";
    case "missing": return "text-[var(--color-muted)]";
  }
}

function queueColor(len: number, max: number): string {
  if (!max) return "text-[var(--color-text-2)]";
  const ratio = len / max;
  if (ratio >= 0.8) return "text-danger";
  if (ratio >= 0.5) return "text-warning";
  return "text-[var(--color-text-2)]";
}

function fmtAge(s: number | null): string {
  if (s == null) return "nunca corrió";
  if (s < 60) return `hace ${s}s`;
  if (s < 3600) return `hace ${Math.floor(s / 60)}min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)}h`;
  return `hace ${Math.floor(s / 86400)}d`;
}

function ProtocolBlock({ name, queue, max, dropped, flushMs }:
  { name: string; queue: number; max: number; dropped: number; flushMs: number }) {
  return (
    <div className="flex-1 min-w-[180px]">
      <p className="text-xs font-semibold text-[var(--color-text-2)] uppercase tracking-wider mb-2">{name}</p>
      <div className="space-y-1.5 text-sm">
        <div className="flex justify-between">
          <span className="text-[var(--color-muted)]">Cola</span>
          <span className={`font-mono ${queueColor(queue, max)}`}>{queue} / {max}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--color-muted)]">Descartados</span>
          <span className={`font-mono ${dropped ? "text-danger" : "text-[var(--color-text-2)]"}`}>{dropped}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-[var(--color-muted)]">Último flush</span>
          <span className="font-mono text-[var(--color-text-2)]">{flushMs}ms</span>
        </div>
      </div>
    </div>
  );
}

export default function SystemHealthPage() {
  const [cron, setCron] = useState<CronJob[]>([]);
  const [hep,  setHep]  = useState<any>(null);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [openLogs, setOpenLogs]  = useState<string | null>(null);

  const [otherSvc, setOtherSvc] = useState<{ required: OtherService[]; actionable: OtherService[]; unknown: OtherService[] } | null>(null);
  const [showOther, setShowOther] = useState(false);
  const [acting, setActing] = useState<string | null>(null);
  const [showCliHelp, setShowCliHelp] = useState(false);
  const [error, setError] = useState("");

  const [domain, setDomain] = useState("");
  const [webPort, setWebPort] = useState(80);
  const [domainInput, setDomainInput] = useState("");
  const [portInput, setPortInput] = useState(80);
  const [savingDomain, setSavingDomain] = useState(false);
  const [domainSaved, setDomainSaved] = useState(false);

  const loadDomain = useCallback(async () => {
    try {
      const d = await apiGet("/admin/system/domain");
      setDomain(d.domain); setWebPort(d.web_port);
      setDomainInput(d.domain); setPortInput(d.web_port);
    } catch (e: any) { setError(e.message || "Error cargando el dominio de acceso"); }
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const [c, h, s] = await Promise.all([
        apiGet("/admin/cron-health"),
        apiGet("/admin/hep-stats"),
        apiGet("/admin/services-status"),
      ]);
      setCron(c); setHep(h); setServices(s); setError("");
    } catch (e: any) { setError(e.message || "Error actualizando el estado del sistema"); }
  }, []);

  const loadOther = useCallback(async () => {
    try { setOtherSvc(await apiGet("/admin/system-services")); setError(""); }
    catch (e: any) { setError(e.message || "Error cargando otros servicios"); }
  }, []);

  useEffect(() => {
    loadAll();
    loadDomain();
    const t = setInterval(loadAll, 30000);
    return () => clearInterval(t);
  }, [loadAll, loadDomain]);

  async function saveDomain() {
    setSavingDomain(true); setDomainSaved(false);
    try {
      await apiPut("/admin/system/domain", { domain: domainInput, web_port: portInput });
      setDomain(domainInput); setWebPort(portInput); setDomainSaved(true);
      setTimeout(() => setDomainSaved(false), 3000);
    } catch (e: any) {
      alert(e.message ?? "Error guardando el dominio");
    } finally { setSavingDomain(false); }
  }

  async function toggleService(unit: string, action: "disable" | "enable") {
    const verb = action === "disable" ? "apagar" : "reencender";
    if (!confirm(`¿${verb === "apagar" ? "Apagar" : "Reencender"} ${unit}?`)) return;
    setActing(unit);
    try {
      await apiPost(`/admin/system-services/${unit}/action`, { action });
      await loadOther();
    } catch (e: any) {
      alert(e.message ?? `Error al ${verb} ${unit}`);
    } finally { setActing(null); }
  }

  return (
    <div className="space-y-6">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Salud del sistema</h1>
          <p className="text-sm text-[var(--color-text-2)] mt-1">Cron jobs internos y captura de trazas (mini-Homer) — diagnóstico, no información de negocio</p>
        </div>
        <span className="text-xs text-[var(--color-muted)]">Auto-actualiza cada 30s</span>
      </div>

      {/* Servicios VoxiKam — estado + últimas líneas de log, solo lectura.
          Para reiniciar/detener o seguir logs en vivo: CLI `voxikam -r|-l` por consola. */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-medium text-[var(--color-text-2)] uppercase tracking-wider">Servicios VoxiKam</p>
          <button onClick={() => setShowCliHelp(v => !v)}
            className="focus-ring flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-text-2)] rounded">
            <Terminal size={12} /> reiniciar/logs en vivo: CLI <code className="text-[var(--color-text-2)]">voxikam</code> por consola
            {showCliHelp ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        </div>
        {showCliHelp && (
          <div className="bg-[var(--color-surface)] rounded-lg p-3 mb-3 mt-2 font-mono text-[11px] text-[var(--color-text-2)] space-y-1">
            <p><span className="text-brand-400">voxikam -s</span> [servicio]         <span className="text-[var(--color-muted)]"># ver estado</span></p>
            <p><span className="text-brand-400">voxikam -r</span> [servicio]         <span className="text-[var(--color-muted)]"># reiniciar</span></p>
            <p><span className="text-brand-400">voxikam -p</span> [servicio]         <span className="text-[var(--color-muted)]"># detener</span></p>
            <p><span className="text-brand-400">voxikam -l</span> [servicio] [-n N]  <span className="text-[var(--color-muted)]"># ver logs (en vivo, o -n N últimas líneas)</span></p>
            <p className="pt-1 text-[var(--color-muted)]">servicio: back · front · hep · kamailio · rtpengine · autotune · app (back+front) · all — si se omite, usa "app"</p>
            <p className="pt-1 text-[var(--color-muted)]">ej: <span className="text-[var(--color-text-2)]">voxikam -l kamailio -n 100</span> · <span className="text-[var(--color-text-2)]">voxikam -r back</span> · <span className="text-[var(--color-text-2)]">voxikam -s all</span></p>
            <p className="pt-1 text-[var(--color-muted)]">-r y -p piden sudo; -s y -l no. Se ejecuta por SSH en el server, no desde este panel.</p>
          </div>
        )}
        <div className="divide-y divide-[var(--color-border)]/60 mt-2">
          {services.map(s => {
            const up = s.active_state === "active";
            return (
              <div key={s.unit}>
                <button onClick={() => setOpenLogs(openLogs === s.unit ? null : s.unit)}
                  className="focus-ring w-full flex items-center gap-3 py-2.5 text-left rounded">
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${up ? "bg-success" : "bg-danger"}`} />
                  <span className="text-sm text-[var(--color-text)] flex-1 min-w-0 truncate">{s.label}</span>
                  <span className={`text-xs font-mono flex-shrink-0 ${up ? "text-success" : "text-danger"}`}>
                    {s.sub_state}{s.pid ? ` · pid ${s.pid}` : ""}{s.restarts && s.restarts !== "0" ? ` · ${s.restarts} restarts` : ""}
                  </span>
                  {openLogs === s.unit ? <ChevronDown size={14} className="text-[var(--color-muted)]" /> : <ChevronRight size={14} className="text-[var(--color-muted)]" />}
                </button>
                {openLogs === s.unit && (
                  <div className="bg-[var(--color-surface)] rounded-lg p-3 mb-2 font-mono text-[11px] text-[var(--color-text-2)] space-y-0.5 overflow-x-auto">
                    {s.recent_logs.length ? s.recent_logs.map((l, i) => <div key={i} className="whitespace-pre">{l}</div>)
                      : <div className="text-[var(--color-muted)]">sin líneas recientes</div>}
                  </div>
                )}
              </div>
            );
          })}
          {!services.length && <p className="text-xs text-[var(--color-muted)] py-3">—</p>}
        </div>
      </div>

      {/* Dominio de acceso — nginx y el frontend ya aceptan cualquier
          dominio (server_name catch-all, API relativa /api), lo único
          que necesita saberlo es el backend para CORS. Guardar acá NO
          reinicia nada — aplica en el proceso corriendo al toque. */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">
        <p className="text-xs font-medium text-[var(--color-text-2)] uppercase tracking-wider mb-1">Dominio de acceso</p>
        <p className="text-xs text-[var(--color-muted)] mb-3">
          {domain
            ? <>Acceso actual: <span className="font-mono text-[var(--color-text-2)]">http://{domain}:{webPort}</span></>
            : "Todavía no hay un dominio configurado — se accede por IP/puerto."}
          {" "}Guardar acá no reinicia nada, aplica al toque.
        </p>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={domainInput}
            onChange={e => setDomainInput(e.target.value)}
            placeholder="ej. voxikam.miclientedominio.com"
            className="focus-ring flex-1 min-w-0 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] placeholder:text-[var(--color-muted)]"
          />
          <input
            type="number"
            value={portInput}
            onChange={e => setPortInput(Number(e.target.value))}
            min={1} max={65535}
            className="focus-ring w-24 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)]"
          />
          <button
            onClick={saveDomain}
            disabled={savingDomain || !domainInput}
            className="focus-ring flex-shrink-0 px-3 py-2 rounded-lg text-xs font-medium bg-brand-600/20 text-brand-400 hover:bg-brand-600/30 disabled:opacity-50"
          >
            {savingDomain ? "Guardando…" : domainSaved ? "Guardado ✓" : "Guardar"}
          </button>
        </div>
      </div>

      {/* Cron jobs */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-medium text-[var(--color-text-2)] uppercase tracking-wider">Cron jobs</p>
          <div className="flex items-center gap-3">
            {(["ok", "stale", "error", "missing"] as const).map(s => {
              const n = cron.filter(j => j.status === s).length;
              if (!n) return null;
              return (
                <StatusBadge key={s} variant={cronStatusVariant(s)} dot tight>
                  {n} {CRON_STATUS_LABEL[s]}
                </StatusBadge>
              );
            })}
          </div>
        </div>
        <div className="divide-y divide-[var(--color-border)]/60 mt-2">
          {cron.map(job => (
            <div key={job.key} className="py-2.5">
              <div className="flex items-center gap-3">
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${cronDotCls(job.status)}`} />
                <span className="text-sm text-[var(--color-text)] flex-1 min-w-0 truncate">{job.label}</span>
                <StatusBadge variant={cronStatusVariant(job.status)} tight className="flex-shrink-0 uppercase tracking-wider">
                  {CRON_STATUS_LABEL[job.status]}
                </StatusBadge>
                <span className={`text-xs font-mono flex-shrink-0 ${cronTextCls(job.status)}`}>{fmtAge(job.age_seconds)}</span>
              </div>
              {job.status === "error" && job.last_line && (
                <p className="text-xs font-mono text-danger/70 mt-1 ml-5 truncate" title={job.last_line}>
                  {job.last_line}
                </p>
              )}
            </div>
          ))}
          {!cron.length && <p className="text-xs text-[var(--color-muted)] py-3">—</p>}
        </div>
      </div>

      {/* Cola HEP (mini-Homer) — reorganizado por protocolo (SIP / RTCP) en vez de
          por tipo de métrica, para que cada bloque se lea de corrido */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-xs font-medium text-[var(--color-text-2)] uppercase tracking-wider">Captura de trazas (mini-Homer)</p>
            <p className="text-xs text-[var(--color-muted)] mt-0.5">Cuánto tráfico SIP/RTCP está procesando el listener antes de guardarlo — si la cola se acerca al tope, empieza a descartar</p>
          </div>
          <StatusBadge variant={hep?.available ? "success" : "danger"} dot tight>
            {hep?.available ? "activo" : "sin datos"}
          </StatusBadge>
        </div>
        {hep?.available ? (
          <div className="flex flex-wrap gap-6">
            <ProtocolBlock name="SIP"  queue={hep.sip_queue_len}  max={hep.max_queue} dropped={hep.sip_dropped_total}  flushMs={hep.last_sip_flush_ms} />
            <ProtocolBlock name="RTCP" queue={hep.rtcp_queue_len} max={hep.max_queue} dropped={hep.rtcp_dropped_total} flushMs={hep.last_rtcp_flush_ms} />
            <div className="flex-1 min-w-[180px]" title="Paquetes descartados por el kernel antes de que el proceso los viera — buffer del socket desbordado en una ráfaga">
              <p className="text-xs font-semibold text-[var(--color-text-2)] uppercase tracking-wider mb-2">Kernel</p>
              <div className="flex justify-between text-sm">
                <span className="text-[var(--color-muted)]">Descartes</span>
                <span className={`font-mono ${hep.kernel_udp_drops ? "text-danger" : "text-[var(--color-text-2)]"}`}>
                  {hep.kernel_udp_drops ?? "—"}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-xs text-[var(--color-muted)]">
            Sin datos recientes de voxikam-hep.service — revisar: journalctl -u voxikam-hep -n 20
          </p>
        )}
      </div>

      {/* Otros servicios del sistema — barrido de TODO lo habilitado en el server
          (no solo lo de VoxiKam), para achicar superficie en un SBC de producción.
          Apagar/reencender solo está habilitado para una allowlist chica y conocida
          (backend/routers/system_services.py::ACTIONABLE) — cualquier otro servicio
          "no reconocido" se muestra para transparencia pero sin botón: no reconocido
          no es lo mismo que "seguro de apagar". */}
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl">
        <button onClick={() => { setShowOther(v => !v); if (!otherSvc) loadOther(); }}
          className="focus-ring w-full flex items-center justify-between px-5 py-4 text-sm font-semibold rounded-xl">
          <span>Otros servicios del sistema</span>
          <span className="flex items-center gap-2 text-[var(--color-text-2)] font-normal text-xs">
            barrido completo del server, no solo VoxiKam
            {showOther ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
        </button>
        {showOther && (
          <div className="border-t border-[var(--color-border)] p-5 space-y-5">
            {!otherSvc ? (
              <p className="text-xs text-[var(--color-muted)]">Cargando…</p>
            ) : (
              <>
                {otherSvc.actionable.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-[var(--color-text-2)] uppercase tracking-wider mb-2">
                      Candidatos a apagar ({otherSvc.actionable.length})
                    </p>
                    <div className="space-y-2">
                      {otherSvc.actionable.map(s => (
                        <div key={s.unit} className="flex items-start gap-3 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2.5">
                          <span className={`w-2 h-2 rounded-full flex-shrink-0 mt-1 ${s.running ? "bg-success" : "bg-[var(--color-muted)]"}`} />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-[var(--color-text)]">{s.unit}</p>
                            <p className="text-xs text-[var(--color-muted)] mt-0.5">{s.reason}</p>
                          </div>
                          <button
                            onClick={() => toggleService(s.unit, s.running ? "disable" : "enable")}
                            disabled={acting === s.unit}
                            className={`focus-ring flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium disabled:opacity-50 ${
                              s.running ? "bg-danger/15 text-danger hover:bg-danger/25" : "bg-success/15 text-success hover:bg-success/25"
                            }`}>
                            {s.running ? <PowerOff size={12} /> : <Power size={12} />}
                            {acting === s.unit ? "..." : s.running ? "Apagar" : "Reencender"}
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <p className="text-xs font-medium text-[var(--color-text-2)] uppercase tracking-wider mb-2">
                    Necesarios ({otherSvc.required.length})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {otherSvc.required.map(s => (
                      <span key={s.unit} className="text-xs font-mono text-[var(--color-muted)] bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-1">
                        {s.unit}
                      </span>
                    ))}
                  </div>
                </div>

                {otherSvc.unknown.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-[var(--color-text-2)] uppercase tracking-wider mb-2">
                      No reconocidos ({otherSvc.unknown.length}) — revisar por consola, sin acción acá
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {otherSvc.unknown.map(s => (
                        <span key={s.unit} className="text-xs font-mono text-warning/80 bg-warning/10 border border-warning/30 rounded px-2 py-1">
                          {s.unit}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
