"use client";
import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost, apiDelete, apiPut } from "@/lib/api";
import { Plus, Trash2, Pencil, X, ChevronRight } from "lucide-react";
import Link from "next/link";

interface FirewallRule {
  id: number; ip: string; action: string;
  service: string; jail: boolean; description: string;
}
interface CustomerIP  { id: number; ip: string; description: string | null }
interface CustomerRow { id: number; name: string; techprefix: string; ips: CustomerIP[] }

const SERVICES = [
  { value: "all", label: "Todos (SIP + RTP)", port: "" },
  { value: "sip", label: "SIP — 5060 UDP/TCP", port: "5060" },
  { value: "rtp", label: "RTP — 20000-40000 UDP", port: "20k-40k" },
  { value: "ssh", label: "SSH — 32451 TCP", port: "32451" },
] as const;

function svcBadge(svc: string) {
  switch (svc) {
    case "sip": return { label: "SIP :5060",    cls: "bg-blue-900/30 text-blue-400 border border-blue-800/40" };
    case "rtp": return { label: "RTP :20k-40k", cls: "bg-purple-900/30 text-purple-400 border border-purple-800/40" };
    case "ssh": return { label: "SSH :32451",   cls: "bg-amber-900/30 text-amber-400 border border-amber-800/40" };
    default:    return { label: "Todos",         cls: "bg-[var(--color-surface)] text-[var(--color-muted)] border border-[var(--color-border)]" };
  }
}

const EMPTY = { ip: "", action: "allow", service: "all", description: "" };

export default function FirewallPage() {
  const [rules, setRules]         = useState<FirewallRule[]>([]);
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [form, setForm]           = useState<typeof EMPTY>(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving]       = useState(false);
  const formRef                   = useRef<HTMLFormElement>(null);

  const loadRules = () => apiGet("/admin/firewall").then(setRules);

  async function loadCustomers() {
    const list = await apiGet("/admin/customers");
    const details = await Promise.all(
      list.map((c: any) => apiGet(`/admin/customers/${c.id}`))
    );
    setCustomers(details);
  }

  useEffect(() => { loadRules(); loadCustomers(); }, []);

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
    await apiDelete(`/admin/firewall/${id}`); await loadRules();
  }

  const actionBadge = (action: string, jail: boolean) => {
    if (jail) return "bg-red-900/40 text-red-300 border border-red-700";
    return action === "allow"
      ? "bg-green-900/30 text-green-400"
      : "bg-red-900/30 text-red-400";
  };

  const card = "bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl";
  const sel  = "bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Firewall</h1>

      {/* Reglas globales */}
      <div>
        <h2 className="text-sm font-semibold text-[var(--color-text-2)] uppercase tracking-wider mb-3">
          Reglas globales
        </h2>
        <p className="text-xs text-[var(--color-muted)] mb-4">
          ALLOW / DENY para IPs globales. Puedes restringir el ALLOW a un servicio específico (SIP, RTP o SSH).
        </p>

        <form ref={formRef} onSubmit={submit} className={`${card} p-6 mb-4`}>
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

        <div className={`${card} overflow-hidden`}>
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
                      <span className={`px-2 py-0.5 rounded-full text-xs ${actionBadge(r.action, r.jail)}`}>
                        {r.jail ? "JAIL" : r.action.toUpperCase()}
                      </span>
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

      {/* IPs por cliente */}
      <div>
        <h2 className="text-sm font-semibold text-[var(--color-text-2)] uppercase tracking-wider mb-3">
          IPs autorizadas por cliente
        </h2>
        <p className="text-xs text-[var(--color-muted)] mb-4">
          Vista consolidada. Para agregar o eliminar IPs de un cliente, abre su perfil.
        </p>

        <div className={`${card} overflow-hidden`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                <th className="px-6 py-3 text-left">Cliente</th>
                <th className="px-6 py-3 text-center">Prefijo</th>
                <th className="px-6 py-3 text-left">IPs autorizadas</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody>
              {customers.length === 0 ? (
                <tr><td colSpan={4} className="px-6 py-8 text-center text-[var(--color-muted)] text-sm">Sin clientes</td></tr>
              ) : customers.map(c => (
                <tr key={c.id} className="border-b border-[var(--color-border)]/50 hover:bg-white/2">
                  <td className="px-6 py-3 font-medium">{c.name}</td>
                  <td className="px-6 py-3 text-center font-mono text-brand-400">{c.techprefix}</td>
                  <td className="px-6 py-3">
                    {c.ips.length === 0 ? (
                      <span className="text-[var(--color-muted)] text-xs italic">Sin IPs — trunk SIP bloqueado</span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {c.ips.map(ip => (
                          <span key={ip.id}
                            className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-0.5 font-mono text-xs text-brand-400"
                            title={ip.description ?? undefined}>
                            {ip.ip}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-3 text-right">
                    <Link href={`/customers/${c.id}`}
                      className="text-[var(--color-muted)] hover:text-brand-400 transition-colors inline-flex items-center gap-1 text-xs">
                      Editar <ChevronRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
