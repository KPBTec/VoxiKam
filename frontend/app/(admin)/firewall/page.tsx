"use client";
import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost, apiDelete, apiPut } from "@/lib/api";
import { Plus, Trash2, Pencil, X, Lock, Unlock } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorBanner } from "@/components/ErrorBanner";

interface FirewallRule {
  id: number; ip: string; action: string;
  service: string; jail: boolean; description: string;
}

const SERVICES = [
  { value: "all",  label: "Todos (SIP + RTP)", port: "" },
  { value: "sip",  label: "SIP — 5060 UDP/TCP", port: "5060" },
  { value: "rtp",  label: "RTP — 20000-40000 UDP", port: "20k-40k" },
  { value: "ssh",  label: "SSH — 32451 TCP", port: "32451" },
  { value: "icmp", label: "ICMP — ping", port: "" },
] as const;

// Estas son etiquetas de CATEGORÍA (qué puerto/servicio es), no de severidad —
// por eso usan un estilo neutro propio en vez de los tokens success/warning/danger
// que StatusBadge reserva para "todo bien / atención / error" en el resto de la
// app. Antes reusaban esos mismos tokens como color de puerto (ssh=warning,
// icmp=success), lo que hacía pensar que ICMP "está bien" y SSH "tiene un
// problema" — no es así, son solo 4 etiquetas de puerto sin jerarquía entre sí.
const SVC_TAG_CLS = "bg-[var(--color-surface)] text-[var(--color-text-2)] border border-[var(--color-border-2)]";
function svcBadge(svc: string) {
  switch (svc) {
    case "sip":  return { label: "SIP :5060",    cls: SVC_TAG_CLS };
    case "rtp":  return { label: "RTP :20k-40k", cls: SVC_TAG_CLS };
    case "ssh":  return { label: "SSH :32451",   cls: SVC_TAG_CLS };
    case "icmp": return { label: "ICMP (ping)",  cls: SVC_TAG_CLS };
    default:     return { label: "Todos",         cls: "bg-[var(--color-surface)] text-[var(--color-muted)] border border-[var(--color-border)]" };
  }
}

const EMPTY = { ip: "", action: "allow", service: "all", description: "" };

export default function FirewallPage() {
  const [rules, setRules]         = useState<FirewallRule[]>([]);
  const [form, setForm]           = useState<typeof EMPTY>(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving]       = useState(false);
  const formRef                   = useRef<HTMLFormElement>(null);
  const [error, setError]         = useState("");

  const loadRules = () => apiGet("/admin/firewall").then(r => { setRules(r); setError(""); }).catch((e: any) => setError(e.message || "Error cargando reglas"));

  useEffect(() => { loadRules(); }, []);

  function startEdit(r: FirewallRule) {
    setEditingId(r.id);
    setForm({ ip: r.ip, action: r.action, service: r.service ?? "all", description: r.description ?? "" });
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(EMPTY);
  }

  function setAction(action: string) {
    setForm(f => ({ ...f, action, service: action === "deny" ? "all" : f.service }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setSaving(true);
    try {
      if (editingId) {
        await apiPut(`/admin/firewall/${editingId}`, form);
        setEditingId(null);
      } else {
        await apiPost("/admin/firewall", form);
      }
      await loadRules();
      setForm(EMPTY);
    } finally { setSaving(false); }
  }

  async function del(id: number) {
    if (!confirm("¿Eliminar esta regla de firewall? El tráfico que dependía de ella dejará de estar permitido/bloqueado.")) return;
    try { await apiDelete(`/admin/firewall/${id}`); await loadRules(); }
    catch (e: any) { setError(e.message || "Error al eliminar la regla"); }
  }

  const [jailing, setJailing] = useState<number | null>(null);
  async function toggleJail(id: number, jail: boolean) {
    setJailing(id);
    try {
      await apiPost(`/admin/firewall/${id}/jail?jail=${jail}`, {});
      await loadRules();
    } catch (e: any) {
      setError(e.message || `Error al ${jail ? "poner en jail" : "liberar"} la regla`);
    } finally { setJailing(null); }
  }

  const card = "bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl";
  const sel  = "bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Firewall</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Reglas globales ALLOW/DENY. Las IPs autorizadas por cliente viven en{" "}
          <a href="/security/customer-ips" className="underline">Seguridad → IPs de clientes</a>, y los baneos
          automáticos en <a href="/security/fail2ban" className="underline">Seguridad → Fail2ban</a>.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <form ref={formRef} onSubmit={submit} className={`${card} p-6`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">
            {editingId ? "Editar regla" : "Agregar regla global"}
          </h3>
          {editingId && (
            <button type="button" onClick={cancelEdit}
              className="flex items-center gap-1 text-xs text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors">
              <X size={14} /> Cancelar
            </button>
          )}
        </div>
        <div className="flex gap-3 flex-wrap">
          <input required placeholder="IP o CIDR (ej: 1.2.3.4 o 10.0.0.0/8)"
            value={form.ip} onChange={e => setForm(f => ({ ...f, ip: e.target.value }))}
            className="flex-1 min-w-48 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />

          <select value={form.action} onChange={e => setAction(e.target.value)} className={sel}>
            <option value="allow">ALLOW</option>
            <option value="deny">DENY</option>
          </select>

          {form.action === "allow" && (
            <select value={form.service} onChange={e => setForm(f => ({ ...f, service: e.target.value }))} className={sel}>
              {SERVICES.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          )}

          <input placeholder="Descripción (opcional)"
            value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            className="flex-1 min-w-48 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />

          <button type="submit" disabled={saving}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm px-4 py-2 rounded-lg transition-colors disabled:opacity-50">
            {editingId
              ? (saving ? "Guardando..." : "Guardar cambios")
              : (<><Plus size={16} /> {saving ? "Aplicando..." : "Agregar"}</>)
            }
          </button>
        </div>
      </form>

      <div className={`${card} overflow-x-auto`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
              <th className="px-6 py-3 text-left">IP / CIDR</th>
              <th className="px-6 py-3 text-center">Acción</th>
              <th className="px-6 py-3 text-center">Puerto</th>
              <th className="px-6 py-3 text-left">Descripción</th>
              <th className="px-6 py-3" />
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-[var(--color-muted)] text-sm">Sin reglas globales</td></tr>
            ) : rules.map(r => {
              const svc = svcBadge(r.service ?? "all");
              const isEditing = editingId === r.id;
              return (
                <tr key={r.id} className={`border-b border-[var(--color-border)]/50 hover:bg-white/2 ${r.jail ? "opacity-70" : ""} ${isEditing ? "bg-brand-900/10" : ""}`}>
                  <td className="px-6 py-3 font-mono">{r.ip}</td>
                  <td className="px-6 py-3 text-center">
                    <StatusBadge variant={r.jail ? 'danger' : (r.action === 'allow' ? 'success' : 'danger')} bordered={r.jail}>
                      {r.jail ? "JAIL" : r.action.toUpperCase()}
                    </StatusBadge>
                  </td>
                  <td className="px-6 py-3 text-center">
                    {r.action === "allow" && (
                      <span className={`px-2 py-0.5 rounded text-xs font-mono ${svc.cls}`}>{svc.label}</span>
                    )}
                  </td>
                  <td className="px-6 py-3 text-[var(--color-text-2)]">{r.description}</td>
                  <td className="px-6 py-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      {!r.jail && (
                        <button onClick={() => isEditing ? cancelEdit() : startEdit(r)}
                          className={`transition-colors ${isEditing ? "text-brand-400" : "text-[var(--color-muted)] hover:text-brand-400"}`}>
                          {isEditing ? <X size={15} /> : <Pencil size={14} />}
                        </button>
                      )}
                      <button
                        disabled={jailing === r.id}
                        onClick={() => toggleJail(r.id, !r.jail)}
                        title={r.jail ? "Liberar (sacar de jail)" : "Poner en jail (bloqueo forzado)"}
                        className={`transition-colors disabled:opacity-50 ${r.jail ? "text-red-400 hover:text-green-400" : "text-[var(--color-muted)] hover:text-red-400"}`}>
                        {r.jail ? <Unlock size={14} /> : <Lock size={14} />}
                      </button>
                      <button onClick={() => del(r.id)}
                        className="text-[var(--color-muted)] hover:text-danger transition-colors">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
