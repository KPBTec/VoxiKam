"use client";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { Plus, ChevronRight } from "lucide-react";
import Link from "next/link";

export default function CustomersPage() {
  const [rows, setRows]         = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm]         = useState({ name: "", email: "", techprefix: "", cpslimit: 2, calllimit: 10 });
  const [saving, setSaving]     = useState(false);

  useEffect(() => { apiGet("/admin/customers").then(setRows); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setSaving(true);
    try {
      await apiPost("/admin/customers", form);
      setShowForm(false);
      setRows(await apiGet("/admin/customers"));
    } finally { setSaving(false); }
  }

  const badge = (status: string) => {
    const map: Record<string, string> = {
      active:    "bg-green-900/30 text-green-400",
      suspended: "bg-yellow-900/30 text-yellow-400",
      expired:   "bg-red-900/30 text-red-400",
    };
    return `px-2 py-0.5 rounded-full text-xs ${map[status] ?? ""}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Clientes</h1>
        <button onClick={() => setShowForm(true)}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm px-4 py-2 rounded-lg transition-colors">
          <Plus size={16} /> Nuevo cliente
        </button>
      </div>

      {showForm && (
        <form onSubmit={create}
          className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl p-6 space-y-4">
          <h2 className="font-semibold">Nuevo cliente</h2>
          <div className="grid grid-cols-2 gap-4">
            {[
              ["Nombre",  "name",       "text", "Empresa ABC"],
              ["Email",   "email",      "email","contacto@empresa.com"],
              ["Prefijo", "techprefix", "text", "1001"],
            ].map(([label, key, type, placeholder]) => (
              <div key={key} className="space-y-1">
                <label className="text-xs text-[var(--color-text-2)] uppercase tracking-wider">{label}</label>
                <input type={type} placeholder={placeholder} required={key !== "email" ? true : false}
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
          </div>
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

      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-hidden">
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
              <tr key={r.id} className="border-b border-[var(--color-border)]/50 hover:bg-white/2">
                <td className="px-6 py-3 font-medium">{r.name}</td>
                <td className="px-6 py-3 text-[var(--color-text-2)]">{r.email}</td>
                <td className="px-6 py-3 text-center font-mono text-brand-400">{r.techprefix}</td>
                <td className="px-6 py-3 text-center">{r.cpslimit}</td>
                <td className="px-6 py-3 text-center">{r.calllimit}</td>
                <td className="px-6 py-3 text-center">S/. {parseFloat(r.balance).toFixed(2)}</td>
                <td className="px-6 py-3 text-center">
                  <span className={badge(r.status)}>{r.status}</span>
                </td>
                <td className="px-6 py-3 text-right">
                  <Link href={`/customers/${r.id}`}
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
