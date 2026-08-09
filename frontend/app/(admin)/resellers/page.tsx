"use client";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { ChevronRight, Users } from "lucide-react";
import Link from "next/link";
import { StatusBadge, customerStatusVariant } from "@/components/StatusBadge";
import { Balance } from "@/components/Balance";

export default function ResellersPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [showDeleted, setShowDeleted] = useState(false);
  const [loading, setLoading] = useState(true);

  const reload = (includeDeleted: boolean) =>
    apiGet(`/admin/customers?resellers_only=true${includeDeleted ? "&include_deleted=true" : ""}`)
      .then(setRows).finally(() => setLoading(false));

  useEffect(() => { reload(showDeleted); }, [showDeleted]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Resellers</h1>
          <p className="text-sm text-[var(--color-text-2)] mt-0.5">
            Clientes convertidos en reseller — venden a sus propios sub-clientes con sus propias tarifas y carriers.
            Si se desactiva un reseller, se queda acá listado como inactivo (no desaparece).
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--color-text-2)] cursor-pointer select-none">
          <input type="checkbox" checked={showDeleted} onChange={e => setShowDeleted(e.target.checked)} />
          Mostrar desactivados
        </label>
      </div>

      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
              <th className="px-6 py-3 text-left">Nombre</th>
              <th className="px-6 py-3 text-left">Email</th>
              <th className="px-6 py-3 text-center">Prefijo</th>
              <th className="px-6 py-3 text-center">Sub-clientes</th>
              <th className="px-6 py-3 text-center">Balance</th>
              <th className="px-6 py-3 text-center">Estado</th>
              <th className="px-6 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={`border-b border-[var(--color-border)]/50 hover:bg-white/2 ${r.status !== "active" ? "opacity-50" : ""}`}>
                <td className="px-6 py-3 font-medium">{r.name}</td>
                <td className="px-6 py-3 text-[var(--color-text-2)]">{r.email}</td>
                <td className="px-6 py-3 text-center font-mono text-brand-400">{r.techprefix}</td>
                <td className="px-6 py-3 text-center">
                  <span className="inline-flex items-center gap-1.5">
                    <Users size={13} className="text-[var(--color-muted)]" /> {r.sub_customer_count}
                  </span>
                </td>
                <td className="px-6 py-3 text-center"><Balance amount={r.balance} /></td>
                <td className="px-6 py-3 text-center">
                  <StatusBadge variant={customerStatusVariant(r.status)}>
                    {r.status === "active" ? "active" : `${r.status} · inactivo`}
                  </StatusBadge>
                </td>
                <td className="px-6 py-3 text-right">
                  <Link href={`/customers/${r.id}`} aria-label="Ver detalle"
                    className="text-[var(--color-muted)] hover:text-brand-400 transition-colors">
                    <ChevronRight size={16} />
                  </Link>
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={7} className="px-6 py-10 text-center text-[var(--color-muted)] text-sm">
                Sin resellers todavía — convertí un cliente desde su ficha (Clientes → detalle → "Convertir en reseller").
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
