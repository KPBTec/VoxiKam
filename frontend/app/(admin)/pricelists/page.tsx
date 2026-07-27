'use client'
import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete, apiUpload, apiFetch } from '@/lib/api'
import { Plus, Send, Trash2, FileStack, Upload, Download } from 'lucide-react'

interface Plan { id: number; name: string }
interface Draft {
  id: number; label: string; status: 'draft' | 'published' | 'discarded'
  rate_plan_id: number; rate_plan_name: string; item_count: number; created_at: string
}
interface Prefix { id: number; prefix: string; destination: string; group_name: string }
interface DraftItem {
  prefix_id: number; prefix: string; destination: string; group_name: string
  new_rateinitial: string; new_connectcharge: string
  current_rateinitial: string | null; current_connectcharge: string | null
}

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'

export default function PricelistsPage() {
  const [plans, setPlans] = useState<Plan[]>([])
  const [planId, setPlanId] = useState('')
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [newLabel, setNewLabel] = useState('')

  const [openDraft, setOpenDraft] = useState<Draft | null>(null)
  const [items, setItems] = useState<DraftItem[]>([])
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [addForm, setAddForm] = useState({ prefix_id: '', rateinitial: '', connectcharge: '0' })
  const [error, setError] = useState('')

  async function loadPlans() {
    try {
      const p = await apiGet('/admin/rates/plans')
      setPlans(p)
      if (p.length && !planId) setPlanId(String(p[0].id))
    } catch (e: any) { setError(e.message || 'Error cargando planes') }
  }
  async function loadDrafts(pid: string) {
    if (!pid) return
    try { setDrafts(await apiGet(`/admin/pricelists/drafts?rate_plan_id=${pid}`)) }
    catch (e: any) { setError(e.message || 'Error cargando drafts') }
  }
  useEffect(() => { loadPlans(); apiGet('/admin/rates/prefixes').then(setPrefixes).catch((e: any) => setError(e.message)) }, [])
  useEffect(() => { loadDrafts(planId) }, [planId])

  async function createDraft(e: React.FormEvent) {
    e.preventDefault()
    await apiPost('/admin/pricelists/drafts', { rate_plan_id: parseInt(planId), label: newLabel })
    setNewLabel('')
    loadDrafts(planId)
  }

  async function openDraftDetail(d: Draft) {
    const r = await apiGet(`/admin/pricelists/drafts/${d.id}`)
    setOpenDraft(d)
    setItems(r.items)
  }

  async function addItem(e: React.FormEvent) {
    e.preventDefault()
    if (!openDraft || !addForm.prefix_id) return
    await apiPut(`/admin/pricelists/drafts/${openDraft.id}/items`, [{
      prefix_id: parseInt(addForm.prefix_id),
      rateinitial: parseFloat(addForm.rateinitial),
      connectcharge: parseFloat(addForm.connectcharge) || 0,
    }])
    setAddForm({ prefix_id: '', rateinitial: '', connectcharge: '0' })
    openDraftDetail(openDraft)
  }

  async function removeItem(prefixId: number) {
    if (!openDraft) return
    await apiDelete(`/admin/pricelists/drafts/${openDraft.id}/items/${prefixId}`)
    openDraftDetail(openDraft)
  }

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importResult, setImportResult] = useState<{ imported: number; errors: string[] } | null>(null)

  async function importCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !openDraft) return
    setImportResult(null)
    const r = await apiUpload(`/admin/pricelists/drafts/${openDraft.id}/import-csv`, file)
    setImportResult(r)
    openDraftDetail(openDraft)
  }

  async function downloadDraftCsv() {
    if (!openDraft) return
    const res = await apiFetch(`/admin/pricelists/drafts/${openDraft.id}/export-csv`)
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `draft_${openDraft.id}.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  async function downloadLiveRatesCsv() {
    if (!planId) return
    const res = await apiFetch(`/admin/rates/plans/${planId}/rates/export-csv`)
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `rates_plan_${planId}.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  async function publish() {
    if (!openDraft) return
    if (!confirm(`¿Publicar ${items.length} tarifa(s) de "${openDraft.label}"? Esto actualiza rates en vivo — afecta la facturación de inmediato.`)) return
    await apiPost(`/admin/pricelists/drafts/${openDraft.id}/publish`, {})
    setOpenDraft(null)
    loadDrafts(planId)
  }

  async function discard() {
    if (!openDraft) return
    if (!confirm(`¿Descartar el draft "${openDraft.label}"? No se puede deshacer.`)) return
    await apiPost(`/admin/pricelists/drafts/${openDraft.id}/discard`, {})
    setOpenDraft(null)
    loadDrafts(planId)
  }

  const fmt = (n: string | number | null) => n == null ? '—' : parseFloat(String(n)).toFixed(6)
  const pctChange = (oldV: string | null, newV: string) => {
    if (oldV == null) return null
    const o = parseFloat(oldV), n = parseFloat(newV)
    if (o === 0) return null
    return ((n - o) / o * 100)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Pricelists</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Borrador y aprobación de tarifas antes de tocar el plan en vivo — el billing worker solo lee
          tarifas ya publicadas, nunca un draft. Revisá el diff antes de publicar.
        </p>
      </div>

      {error && <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">{error}</div>}

      <div className={`${card} p-5 space-y-4`}>
        <div className="flex items-end justify-between gap-3">
          <div className="flex-1">
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Plan de tarifas</label>
            <select value={planId} onChange={e => { setPlanId(e.target.value); setOpenDraft(null) }}
              className="w-full max-w-xs bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm">
              {plans.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <button onClick={downloadLiveRatesCsv} disabled={!planId} type="button"
            className="flex items-center gap-1.5 px-3 py-2 border border-[var(--color-border)] hover:border-brand-500 disabled:opacity-50 text-xs font-medium rounded-lg">
            <Download size={13} /> Exportar tarifas en vivo (CSV)
          </button>
        </div>

        <form onSubmit={createDraft} className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Nuevo draft</label>
            <input required value={newLabel} onChange={e => setNewLabel(e.target.value)}
              placeholder="Ajuste tarifas USA — julio 2026"
              className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
          </div>
          <button type="submit" disabled={!planId}
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
            <Plus size={13} /> Crear draft
          </button>
        </form>
      </div>

      <div className={`${card} overflow-x-auto`}>
        <div className="px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold text-sm flex items-center gap-2"><FileStack size={15} /> Drafts</h2>
        </div>
        {drafts.length === 0 ? (
          <div className="text-[var(--color-muted)] p-8 text-center text-sm">Sin drafts para este plan</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="px-5 py-3 text-left">Label</th>
                <th className="px-5 py-3 text-center">Estado</th>
                <th className="px-5 py-3 text-right">Tarifas</th>
                <th className="px-5 py-3 text-left">Creado</th>
              </tr>
            </thead>
            <tbody>
              {drafts.map(d => (
                <tr key={d.id} onClick={() => d.status === 'draft' ? openDraftDetail(d) : null}
                  className={`border-b border-[var(--color-border)]/50 ${d.status === 'draft' ? 'cursor-pointer hover:bg-white/5' : 'opacity-50'}`}>
                  <td className="px-5 py-2.5">{d.label}</td>
                  <td className="px-5 py-2.5 text-center text-xs">
                    <span className={
                      d.status === 'draft' ? 'text-yellow-400' : d.status === 'published' ? 'text-green-400' : 'text-[var(--color-muted)]'
                    }>{d.status}</span>
                  </td>
                  <td className="px-5 py-2.5 text-right">{d.item_count}</td>
                  <td className="px-5 py-2.5 text-xs text-[var(--color-muted)]">{new Date(d.created_at).toLocaleString('es-PE')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {openDraft && (
        <div className={`${card} p-5 space-y-4`}>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="font-semibold text-sm">Editando: {openDraft.label}</h2>
            <div className="flex gap-2">
              <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={importCsv} />
              <button onClick={() => fileInputRef.current?.click()} type="button"
                className="flex items-center gap-1.5 px-3 py-1.5 border border-[var(--color-border)] hover:border-brand-500 text-xs font-medium rounded-lg">
                <Upload size={13} /> Importar CSV
              </button>
              <button onClick={downloadDraftCsv} type="button" disabled={items.length === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 border border-[var(--color-border)] hover:border-brand-500 disabled:opacity-50 text-xs font-medium rounded-lg">
                <Download size={13} /> Exportar draft
              </button>
              <button onClick={discard}
                className="px-3 py-1.5 border border-[var(--color-border)] hover:border-red-500 text-xs font-medium rounded-lg">
                Descartar
              </button>
              <button onClick={publish} disabled={items.length === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
                <Send size={13} /> Publicar ({items.length})
              </button>
            </div>
          </div>

          {importResult && (
            <div className={`text-xs rounded-lg p-3 ${importResult.errors.length ? 'bg-yellow-950/30 border border-yellow-800/40' : 'bg-green-950/30 border border-green-800/40'}`}>
              <p className={importResult.errors.length ? 'text-yellow-300' : 'text-green-300'}>
                {importResult.imported} tarifa(s) importada(s){importResult.errors.length ? `, ${importResult.errors.length} con error` : ''}
              </p>
              {importResult.errors.map((e, i) => <p key={i} className="text-yellow-400/80 mt-1">{e}</p>)}
            </div>
          )}

          <form onSubmit={addItem} className="grid grid-cols-[2fr_1fr_1fr_auto] gap-3 items-end">
            <div>
              <label className="block text-xs text-[var(--color-text-2)] mb-1">Prefijo</label>
              <select required value={addForm.prefix_id} onChange={e => setAddForm(f => ({ ...f, prefix_id: e.target.value }))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm">
                <option value="">Seleccionar...</option>
                {prefixes.map(p => <option key={p.id} value={p.id}>{p.prefix} — {p.destination}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-[var(--color-text-2)] mb-1">S/./min</label>
              <input required type="number" step="0.000001" value={addForm.rateinitial}
                onChange={e => setAddForm(f => ({ ...f, rateinitial: e.target.value }))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-[var(--color-text-2)] mb-1">Cargo conexión</label>
              <input type="number" step="0.000001" value={addForm.connectcharge}
                onChange={e => setAddForm(f => ({ ...f, connectcharge: e.target.value }))}
                className="w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm" />
            </div>
            <button type="submit" className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-xs font-medium rounded-lg">
              Agregar
            </button>
          </form>

          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-2)] text-xs uppercase border-b border-[var(--color-border)]">
                <th className="text-left pb-2">Prefijo</th>
                <th className="text-right pb-2">Actual</th>
                <th className="text-right pb-2">Nuevo</th>
                <th className="text-right pb-2">Cambio</th>
                <th className="text-right pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => {
                const pct = pctChange(it.current_rateinitial, it.new_rateinitial)
                return (
                  <tr key={it.prefix_id} className="border-b border-[var(--color-border)]/30">
                    <td className="py-2">{it.prefix} — {it.destination}</td>
                    <td className="py-2 text-right font-mono text-[var(--color-muted)]">{fmt(it.current_rateinitial)}</td>
                    <td className="py-2 text-right font-mono">{fmt(it.new_rateinitial)}</td>
                    <td className={`py-2 text-right font-mono text-xs ${
                      pct == null ? 'text-[var(--color-muted)]' : pct > 0 ? 'text-red-400' : pct < 0 ? 'text-green-400' : 'text-[var(--color-muted)]'
                    }`}>
                      {it.current_rateinitial == null ? 'nuevo' : pct == null ? '—' : `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`}
                    </td>
                    <td className="py-2 text-right">
                      <button onClick={() => removeItem(it.prefix_id)} className="text-[var(--color-muted)] hover:text-red-400">
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                )
              })}
              {items.length === 0 && (
                <tr><td colSpan={5} className="py-6 text-center text-[var(--color-muted)] text-sm">Sin tarifas en este draft todavía</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
