"use client";
import { useEffect, useState } from "react";
import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";
import { Plus, Trash2, X, Pencil, Save } from "lucide-react";
import { ErrorBanner } from "@/components/ErrorBanner";

interface CustomerIP  { id: number; ip: string; description: string | null }
interface CustomerRow { id: number; name: string; techprefix: string; ips: CustomerIP[] }

// Separada de /firewall a pedido — antes vivía mezclada ahí (y antes de eso,
// en la ficha del cliente, de donde ya se había sacado a propósito en un
// pase de UI anterior de esta misma sesión). Mismos endpoints de siempre.
// La tabla principal solo lista clientes — hacer clic abre un popup con el
// detalle de IPs de ESE cliente (crear/editar/borrar), en vez de mostrar
// todas las IPs de todos los clientes sueltas en la fila (ilegible cuando
// un cliente tiene 10+ IPs, ver Qubos).
export default function CustomerIpsPage() {
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState("");
  const [open, setOpen]           = useState<CustomerRow | null>(null);

  async function loadCustomers() {
    setLoading(true);
    try {
      const list = await apiGet("/admin/customers");
      const details = await Promise.all(
        list.map((c: any) => apiGet(`/admin/customers/${c.id}`))
      );
      setCustomers(details);
      setError("");
    } catch (e: any) { setError(e.message || "Error cargando clientes"); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadCustomers(); }, []);

  // El popup necesita quedar sincronizado con la fila recién actualizada —
  // sin esto, tras agregar/editar/borrar una IP el popup seguía mostrando
  // el snapshot viejo hasta cerrarlo y reabrirlo.
  async function refreshAndReopen(customerId: number) {
    await loadCustomers();
    const fresh = await apiGet(`/admin/customers/${customerId}`);
    setOpen(fresh);
  }

  const card = "bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">IPs autorizadas por cliente</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          IPs o CIDRs desde los que cada cliente puede enviar tráfico SIP — hacé clic en un cliente
          para ver, agregar, editar o borrar sus IPs.
        </p>
      </div>

      {error && !open && <ErrorBanner>{error}</ErrorBanner>}

      <div className={`${card} overflow-x-auto`}>
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
            {loading ? (
              <tr><td colSpan={4} className="px-6 py-8 text-center text-[var(--color-muted)] text-sm">Cargando...</td></tr>
            ) : customers.length === 0 ? (
              <tr><td colSpan={4} className="px-6 py-8 text-center text-[var(--color-muted)] text-sm">Sin clientes</td></tr>
            ) : customers.map(c => (
              <tr key={c.id} onClick={() => setOpen(c)}
                className="border-b border-[var(--color-border)]/50 hover:bg-white/3 cursor-pointer transition-colors">
                <td className="px-6 py-3 font-medium">{c.name}</td>
                <td className="px-6 py-3 text-center font-mono text-brand-400">{c.techprefix}</td>
                <td className="px-6 py-3">
                  {c.ips.length === 0 ? (
                    <span className="text-[var(--color-muted)] text-xs italic">Sin IPs — trunk SIP bloqueado</span>
                  ) : (
                    <span className="text-xs text-[var(--color-text-2)]">
                      {c.ips.length} IP{c.ips.length > 1 ? "s" : ""}
                    </span>
                  )}
                </td>
                <td className="px-6 py-3 text-right">
                  <span className="text-xs text-brand-400">Ver / editar →</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <CustomerIpsModal
          customer={open}
          onClose={() => setOpen(null)}
          onChanged={() => refreshAndReopen(open.id)}
        />
      )}
    </div>
  );
}

function CustomerIpsModal({ customer, onClose, onChanged }: {
  customer: CustomerRow; onClose: () => void; onChanged: () => void;
}) {
  const [error, setError]       = useState("");
  const [saving, setSaving]     = useState(false);

  const [newIp, setNewIp]         = useState("");
  const [newIpDesc, setNewIpDesc] = useState("");

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editIp, setEditIp]       = useState("");
  const [editDesc, setEditDesc]   = useState("");

  function startEdit(ip: CustomerIP) {
    setEditingId(ip.id); setEditIp(ip.ip); setEditDesc(ip.description ?? "");
  }

  async function addIp(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError("");
    try {
      await apiPost(`/admin/customers/${customer.id}/ips`, { ip: newIp, description: newIpDesc || null });
      setNewIp(""); setNewIpDesc("");
      onChanged();
    } catch (e: any) { setError(e.message || "Error al agregar la IP"); }
    finally { setSaving(false); }
  }

  async function saveEdit(ipId: number) {
    setSaving(true); setError("");
    try {
      await apiPut(`/admin/customers/${customer.id}/ips/${ipId}`, { ip: editIp, description: editDesc || null });
      setEditingId(null);
      onChanged();
    } catch (e: any) { setError(e.message || "Error al editar la IP"); }
    finally { setSaving(false); }
  }

  async function deleteIp(ipId: number) {
    setSaving(true); setError("");
    try {
      await apiDelete(`/admin/customers/${customer.id}/ips/${ipId}`);
      onChanged();
    } catch (e: any) { setError(e.message || "Error al eliminar la IP"); }
    finally { setSaving(false); }
  }

  const inp = "bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-2xl w-full max-w-lg mx-4 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] sticky top-0 bg-[var(--color-card)]">
          <div>
            <h2 className="font-semibold">IPs de {customer.name}</h2>
            <p className="text-xs text-[var(--color-text-2)] font-mono">{customer.techprefix}</p>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {error && <ErrorBanner>{error}</ErrorBanner>}

          {customer.ips.length === 0 ? (
            <p className="text-[var(--color-muted)] text-sm italic">Sin IPs — trunk SIP bloqueado</p>
          ) : (
            <div className="space-y-2">
              {customer.ips.map(ip => (
                <div key={ip.id} className="flex items-center gap-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2">
                  {editingId === ip.id ? (
                    <>
                      <input value={editIp} onChange={e => setEditIp(e.target.value)}
                        className={`${inp} flex-1 font-mono`} autoFocus />
                      <input value={editDesc} onChange={e => setEditDesc(e.target.value)}
                        placeholder="Descripción" className={`${inp} w-40`} />
                      <button onClick={() => saveEdit(ip.id)} disabled={saving}
                        className="text-brand-400 hover:text-brand-300 disabled:opacity-50" title="Guardar" aria-label="Guardar">
                        <Save size={15} />
                      </button>
                      <button onClick={() => setEditingId(null)}
                        className="text-[var(--color-muted)] hover:text-[var(--color-text)]" title="Cancelar" aria-label="Cancelar">
                        <X size={15} />
                      </button>
                    </>
                  ) : (
                    <>
                      <div className="flex-1 min-w-0">
                        <p className="font-mono text-sm text-brand-400">{ip.ip}</p>
                        {ip.description && <p className="text-xs text-[var(--color-text-2)] truncate">{ip.description}</p>}
                      </div>
                      <button onClick={() => startEdit(ip)}
                        className="text-[var(--color-muted)] hover:text-brand-400 transition-colors" title="Editar" aria-label="Editar">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => deleteIp(ip.id)} disabled={saving}
                        className="text-[var(--color-muted)] hover:text-red-400 transition-colors disabled:opacity-50" title="Eliminar" aria-label="Eliminar">
                        <Trash2 size={14} />
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}

          <form onSubmit={addIp} className="flex gap-2 pt-2 border-t border-[var(--color-border)]">
            <input type="text" placeholder="IP o CIDR — ej: 203.0.113.10 o 10.0.0.0/24"
              value={newIp} onChange={e => setNewIp(e.target.value)} required
              className={`${inp} flex-1 min-w-0`} />
            <input type="text" placeholder="Descripción (opcional)"
              value={newIpDesc} onChange={e => setNewIpDesc(e.target.value)}
              className={`${inp} w-32`} />
            <button type="submit" disabled={saving}
              className="flex items-center gap-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-3 py-2 rounded-lg transition-colors flex-shrink-0">
              <Plus size={14} /> Agregar
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
