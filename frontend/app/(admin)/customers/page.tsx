"use client";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { Plus, ChevronRight, Building2 } from "lucide-react";
import Link from "next/link";
import { StatusBadge, customerStatusVariant } from "@/components/StatusBadge";
import { Balance } from "@/components/Balance";

export default function CustomersPage() {
  const [rows, setRows]         = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [showDeleted, setShowDeleted] = useState(false);
  const [form, setForm]         = useState({ name: "", email: "", techprefix: "", cpslimit: 2, calllimit: 10, rate_plan_id: "", is_reseller: false });
  const [ratePlans, setRatePlans] = useState<{ id: number; name: string; currency: string }[]>([]);
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState("");

  const reload = (includeDeleted: boolean) =>
    apiGet(`/admin/customers?exclude_resellers=true${includeDeleted ? "&include_deleted=true" : ""}`).then(r => { setRows(r); setError(""); }).catch((e: any) => setError(e.message || "Error cargando clientes"));

  useEffect(() => { reload(showDeleted); }, [showDeleted]);
  // Plan de tarifas obligatorio al crear — un cliente sin plan nunca genera
  // sessionbill, en silencio (caso real encontrado en producción).
  useEffect(() => { apiGet('/admin/rates/plans').then(setRatePlans).catch(() => {}); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError("");
    if (!form.rate_plan_id) { setError("Seleccioná un plan de tarifas"); setSaving(false); return; }
    try {
      await apiPost("/admin/customers", { ...form, rate_plan_id: +form.rate_plan_id });
      setShowForm(false);
      reload(showDeleted);
    } catch (e: any) { setError(e.message || "Error al crear cliente"); }
    finally { setSaving(false); }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">Clientes</h1>
          <Link href="/resellers" className="flex items-center gap-1.5 text-xs text-[var(--color-muted)] hover:text-brand-400 transition-colors mt-1">
            <Building2 size={13} /> Los resellers tienen su propia lista →
          </Link>
        </div>
        <div className="flex items-center gap-4 flex-wrap">
          {error && <p className="text-danger text-sm">{error}</p>}
          <label className="flex items-center gap-2 text-sm text-[var(--color-text-2)] cursor-pointer select-none">
            <input type="checkbox" checked={showDeleted} onChange={e => setShowDeleted(e.target.checked)} />
            Mostrar desactivados
          </label>
          <button onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm px-4 py-2 rounded-lg transition-colors">
            <Plus size={16} /> Nuevo cliente
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={create}
          className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6 space-y-4">
          <h2 className="font-semibold">Nuevo cliente</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              ["Nombre",  "name",       "text", "Empresa ABC"],
              ["Email",   "email",      "email","contacto@empresa.com"],
              ["Prefijo", "techprefix", "text", "Autogenerado si se deja vacío"],
            ].map(([label, key, type, placeholder]) => (
              <div key={key} className="space-y-1">
                <label className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">{label}</label>
                <input type={type} placeholder={placeholder} required={key !== "email" && key !== "techprefix"}
                  value={(form as any)[key]}
                  onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                  className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
              </div>
            ))}
            <div className="space-y-1">
              <label className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">CPS límite</label>
              <input type="number" value={form.cpslimit}
                onChange={e => setForm(f => ({ ...f, cpslimit: +e.target.value }))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Calls simultáneas</label>
              <input type="number" value={form.calllimit}
                onChange={e => setForm(f => ({ ...f, calllimit: +e.target.value }))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">Plan de tarifas</label>
              {ratePlans.length === 0 ? (
                <p className="text-xs text-yellow-500 py-2">
                  No hay ningún plan creado todavía — <Link href="/rates" className="underline">creá uno primero en Tarifas</Link>.
                </p>
              ) : (
                <select required value={form.rate_plan_id}
                  onChange={e => setForm(f => ({ ...f, rate_plan_id: e.target.value }))}
                  className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500">
                  <option value="">Seleccionar plan...</option>
                  {ratePlans.map(rp => <option key={rp.id} value={rp.id}>{rp.name} ({rp.currency})</option>)}
                </select>
              )}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-[var(--color-text-2)] cursor-pointer select-none">
            <input type="checkbox" checked={form.is_reseller}
              onChange={e => setForm(f => ({ ...f, is_reseller: e.target.checked }))} />
            Crear como reseller
          </label>
          <div className="flex gap-3">
            <button type="submit" disabled={saving}
              className="bg-brand-600 hover:bg-brand-500 text-white text-sm px-4 py-2 rounded-lg transition-colors disabled:opacity-50">
              {saving ? "Guardando..." : "Crear cliente"}
            </button>
            <button type="button" onClick={() => setShowForm(false)}
              className="text-sm text-[var(--color-muted)] hover:text-[var(--color-text)] px-4 py-2">
              Cancelar
            </button>
          </div>
        </form>
      )}

      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
              <th className="px-6 py-3 text-left">Nombre</th>
              <th className="px-6 py-3 text-left">Email</th>
              <th className="px-6 py-3 text-center">Prefijo</th>
              <th className="px-6 py-3 text-center">CPS</th>
              <th className="px-6 py-3 text-center">Calls</th>
              <th className="px-6 py-3 text-center">Balance</th>
              <th className="px-6 py-3 text-center">Estado</th>
              <th className="px-6 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={`border-b border-[var(--color-border)]/50 hover:bg-white/2 ${r.status === "deleted" ? "opacity-50" : ""}`}>
                <td className="px-6 py-3 font-medium">{r.name}</td>
                <td className="px-6 py-3 text-[var(--color-text-2)]">{r.email}</td>
                <td className="px-6 py-3 text-center font-mono text-brand-400">{r.techprefix}</td>
                <td className="px-6 py-3 text-center">{r.cpslimit}</td>
                <td className="px-6 py-3 text-center">{r.calllimit}</td>
                <td className="px-6 py-3 text-center"><Balance amount={r.balance} /></td>
                <td className="px-6 py-3 text-center">
                  <StatusBadge variant={customerStatusVariant(r.status)}>{r.status}</StatusBadge>
                </td>
                <td className="px-6 py-3 text-right">
                  <Link href={`/customers/${r.id}`} aria-label="Ver detalle"
                    className="text-[var(--color-muted)] hover:text-brand-400 transition-colors">
                    <ChevronRight size={16} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
