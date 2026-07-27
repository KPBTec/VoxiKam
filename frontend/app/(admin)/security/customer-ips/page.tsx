"use client";
import { Fragment, useEffect, useState } from "react";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { Plus, Trash2, X } from "lucide-react";
import { ErrorBanner } from "@/components/ErrorBanner";

interface CustomerIP  { id: number; ip: string; description: string | null }
interface CustomerRow { id: number; name: string; techprefix: string; ips: CustomerIP[] }

// Separada de /firewall a pedido — antes vivía mezclada ahí (y antes de eso,
// en la ficha del cliente, de donde ya se había sacado a propósito en un
// pase de UI anterior de esta misma sesión). Mismos endpoints de siempre.
export default function CustomerIpsPage() {
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState("");

  const [addingIpFor, setAddingIpFor] = useState<number | null>(null);
  const [newIp, setNewIp]             = useState("");
  const [newIpDesc, setNewIpDesc]     = useState("");
  const [savingIp, setSavingIp]       = useState(false);
  const [deletingIpId, setDeletingIpId] = useState<number | null>(null);

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

  function toggleAddIp(customerId: number) {
    setAddingIpFor(prev => prev === customerId ? null : customerId);
    setNewIp(""); setNewIpDesc("");
  }

  async function addCustomerIp(e: React.FormEvent, customerId: number) {
    e.preventDefault(); setSavingIp(true);
    try {
      await apiPost(`/admin/customers/${customerId}/ips`, { ip: newIp, description: newIpDesc || null });
      setNewIp(""); setNewIpDesc(""); setAddingIpFor(null);
      await loadCustomers();
    } catch (e: any) { setError(e.message || "Error al agregar la IP"); }
    finally { setSavingIp(false); }
  }

  async function deleteCustomerIp(customerId: number, ipId: number) {
    setDeletingIpId(ipId);
    try {
      await apiDelete(`/admin/customers/${customerId}/ips/${ipId}`);
      await loadCustomers();
    } catch (e: any) { setError(e.message || "Error al eliminar la IP"); }
    finally { setDeletingIpId(null); }
  }

  const card = "bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">IPs autorizadas por cliente</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          IPs o CIDRs desde los que cada cliente puede enviar tráfico SIP — agregá o borrá acá mismo,
          sin salir a la ficha del cliente.
        </p>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

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
              <Fragment key={c.id}>
                <tr className="border-b border-[var(--color-border)]/50 hover:bg-white/2">
                  <td className="px-6 py-3 font-medium align-top">{c.name}</td>
                  <td className="px-6 py-3 text-center font-mono text-brand-400 align-top">{c.techprefix}</td>
                  <td className="px-6 py-3 align-top">
                    {c.ips.length === 0 ? (
                      <span className="text-[var(--color-muted)] text-xs italic">Sin IPs — trunk SIP bloqueado</span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {c.ips.map(ip => (
                          <span key={ip.id}
                            className="flex items-center gap-1.5 bg-[var(--color-surface)] border border-[var(--color-border)] rounded px-2 py-0.5 font-mono text-xs text-brand-400"
                            title={ip.description ?? undefined}>
                            {ip.ip}
                            <button
                              disabled={deletingIpId === ip.id}
                              onClick={() => deleteCustomerIp(c.id, ip.id)}
                              className="text-[var(--color-muted)] hover:text-red-400 transition-colors disabled:opacity-50">
                              <Trash2 size={11} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-3 text-right align-top">
                    <button onClick={() => toggleAddIp(c.id)}
                      className={`inline-flex items-center gap-1 text-xs transition-colors ${addingIpFor === c.id ? "text-brand-400" : "text-[var(--color-muted)] hover:text-brand-400"}`}>
                      {addingIpFor === c.id ? <X size={14} /> : <Plus size={14} />}
                      {addingIpFor === c.id ? "Cancelar" : "Agregar IP"}
                    </button>
                  </td>
                </tr>
                {addingIpFor === c.id && (
                  <tr className="border-b border-[var(--color-border)]/50 bg-brand-900/10">
                    <td colSpan={4} className="px-6 py-3">
                      <form onSubmit={e => addCustomerIp(e, c.id)} className="flex gap-3 flex-wrap items-end">
                        <input type="text" placeholder="IP o CIDR — ej: 203.0.113.10 o 10.0.0.0/24"
                          value={newIp} onChange={e => setNewIp(e.target.value)} required autoFocus
                          className="flex-1 min-w-56 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
                        <input type="text" placeholder="Descripción (opcional)"
                          value={newIpDesc} onChange={e => setNewIpDesc(e.target.value)}
                          className="w-48 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
                        <button type="submit" disabled={savingIp}
                          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors">
                          <Plus size={14} /> {savingIp ? "Agregando..." : "Agregar"}
                        </button>
                      </form>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
