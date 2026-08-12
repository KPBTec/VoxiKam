'use client'
import { useEffect, useState } from 'react'
import { apiGet, apiPut, apiUpload, apiDelete, apiFetch } from '@/lib/api'
import { Save, Image as ImageIcon, Trash2, Palette } from 'lucide-react'

const card = 'bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl'
const inputCls = 'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm disabled:opacity-40'

interface Toggle {
  enabled: boolean
  onToggle: (v: boolean) => void
  title: string
  subtitle: string
  children?: React.ReactNode
}

function ToggleSection({ enabled, onToggle, title, subtitle, children }: Toggle) {
  return (
    <div className={`${card} p-5`}>
      <label className="flex items-start gap-2.5 cursor-pointer select-none mb-3">
        <input type="checkbox" checked={enabled} onChange={e => onToggle(e.target.checked)} className="mt-0.5" />
        <span>
          <span className="block text-sm font-medium">{title}</span>
          <span className="block text-xs text-[var(--color-text-2)] mt-0.5">{subtitle}</span>
        </span>
      </label>
      {enabled && <div className="pl-6 space-y-3">{children}</div>}
    </div>
  )
}

export default function InvoiceTemplatePage() {
  const [logoEnabled, setLogoEnabled] = useState(false)
  const [hasLogo, setHasLogo] = useState(false)
  const [uploadingLogo, setUploadingLogo] = useState(false)
  const [logoUrl, setLogoUrl] = useState<string | null>(null)

  async function loadLogoPreview() {
    try {
      const res = await apiFetch('/admin/invoices/template/logo')
      if (!res.ok) { setLogoUrl(null); return }
      const blob = await res.blob()
      setLogoUrl(prev => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob) })
    } catch { setLogoUrl(null) }
  }

  const [companyEnabled, setCompanyEnabled] = useState(false)
  const [companyName, setCompanyName] = useState('')
  const [companyRuc, setCompanyRuc] = useState('')
  const [companyAddress, setCompanyAddress] = useState('')

  const [footerEnabled, setFooterEnabled] = useState(false)
  const [footerText, setFooterText] = useState('')

  const [accentEnabled, setAccentEnabled] = useState(false)
  const [accentColor, setAccentColor] = useState('#dd8b3d')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const t = await apiGet('/admin/invoices/template')
      setLogoEnabled(t.logo_enabled); setHasLogo(t.has_logo)
      if (t.has_logo) loadLogoPreview()
      setCompanyEnabled(t.company_enabled); setCompanyName(t.company_name); setCompanyRuc(t.company_ruc); setCompanyAddress(t.company_address)
      setFooterEnabled(t.footer_enabled); setFooterText(t.footer_text)
      setAccentEnabled(t.accent_enabled); setAccentColor(t.accent_color)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error cargando la plantilla')
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setSaved(false); setError('')
    try {
      await apiPut('/admin/invoices/template', {
        logo_enabled: logoEnabled,
        company_enabled: companyEnabled, company_name: companyName, company_ruc: companyRuc, company_address: companyAddress,
        footer_enabled: footerEnabled, footer_text: footerText,
        accent_enabled: accentEnabled, accent_color: accentColor,
      })
      setSaved(true)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al guardar')
    } finally { setSaving(false) }
  }

  async function uploadLogo(file: File) {
    setUploadingLogo(true); setError('')
    try {
      await apiUpload('/admin/invoices/template/logo', file)
      setHasLogo(true)
      await loadLogoPreview()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al subir el logo')
    } finally { setUploadingLogo(false) }
  }

  async function removeLogo() {
    if (!confirm('¿Eliminar el logo cargado?')) return
    await apiDelete('/admin/invoices/template/logo')
    setHasLogo(false)
    if (logoUrl) URL.revokeObjectURL(logoUrl)
    setLogoUrl(null)
  }

  if (loading) return <div className="text-[var(--color-muted)] p-8">Cargando...</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Plantilla de factura</h1>
        <p className="text-sm text-[var(--color-text-2)] mt-1">
          Datos de marca opcionales para el PDF de <a href="/invoices" className="underline">Facturas</a> — cada uno con su propio
          check, vos decidís cuáles usar. La estructura del PDF (tabla de llamadas, totales, IGV) no cambia.
        </p>
      </div>

      {error && <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">{error}</div>}

      <form onSubmit={save} className="space-y-4">
        <ToggleSection
          enabled={logoEnabled} onToggle={setLogoEnabled}
          title="Logo"
          subtitle="Se muestra arriba a la izquierda del PDF, antes del título de la factura."
        >
          <div className="flex items-center gap-4">
            {hasLogo && logoUrl ? (
              <img
                src={logoUrl}
                alt="Logo actual"
                className="h-14 bg-white/5 border border-[var(--color-border)] rounded-lg px-3 py-2 object-contain"
              />
            ) : (
              <div className="h-14 w-28 flex items-center justify-center bg-[var(--color-surface)] border border-dashed border-[var(--color-border)] rounded-lg text-[var(--color-muted)]">
                <ImageIcon size={18} />
              </div>
            )}
            <div className="flex items-center gap-2">
              <label className="cursor-pointer px-3 py-2 bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-brand-500 text-xs font-medium rounded-lg">
                {uploadingLogo ? 'Subiendo…' : hasLogo ? 'Cambiar logo' : 'Subir logo'}
                <input type="file" accept=".png,.jpg,.jpeg" className="hidden" disabled={uploadingLogo}
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadLogo(f) }} />
              </label>
              {hasLogo && (
                <button type="button" onClick={removeLogo} aria-label="Quitar logo" className="p-2 text-[var(--color-muted)] hover:text-red-400">
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          </div>
          <p className="text-xs text-[var(--color-muted)]">PNG o JPG. Se recorta a 16mm de alto en el PDF, sin deformar.</p>
        </ToggleSection>

        <ToggleSection
          enabled={companyEnabled} onToggle={setCompanyEnabled}
          title="Encabezado de empresa"
          subtitle="Razón social, RUC y dirección — se muestran arriba del título de la factura."
        >
          <div>
            <label className="block text-xs text-[var(--color-text-2)] mb-1">Razón social</label>
            <input value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="Empresa S.A.C." className={inputCls} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-2)] mb-1">RUC</label>
              <input value={companyRuc} onChange={e => setCompanyRuc(e.target.value)} placeholder="20123456789" className={inputCls} />
            </div>
            <div>
              <label className="block text-xs text-[var(--color-text-2)] mb-1">Dirección</label>
              <input value={companyAddress} onChange={e => setCompanyAddress(e.target.value)} placeholder="Av. Ejemplo 123, Lima" className={inputCls} />
            </div>
          </div>
        </ToggleSection>

        <ToggleSection
          enabled={footerEnabled} onToggle={setFooterEnabled}
          title="Pie de página"
          subtitle="Texto libre al final del PDF (términos, contacto, lo que necesites)."
        >
          <textarea value={footerText} onChange={e => setFooterText(e.target.value)} rows={3}
            placeholder="Gracias por confiar en nosotros. Consultas: contacto@tudominio.com"
            className={`${inputCls} resize-none`} />
        </ToggleSection>

        <ToggleSection
          enabled={accentEnabled} onToggle={setAccentEnabled}
          title="Color de acento"
          subtitle="Reemplaza el ámbar por defecto de VoxiKam en el título, el total y la razón social del PDF."
        >
          <div className="flex items-center gap-3">
            <Palette size={16} className="text-[var(--color-muted)]" />
            <input type="color" value={accentColor} onChange={e => setAccentColor(e.target.value)}
              className="w-12 h-9 bg-transparent border border-[var(--color-border)] rounded cursor-pointer" />
            <input value={accentColor} onChange={e => setAccentColor(e.target.value)} className={`${inputCls} w-32 font-mono`} />
          </div>
        </ToggleSection>

        <div className="flex items-center gap-3">
          <button type="submit" disabled={saving}
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg">
            <Save size={13} /> {saving ? 'Guardando…' : 'Guardar plantilla'}
          </button>
          {saved && <span className="text-xs text-green-400">Guardado — se aplica a la próxima factura generada o regenerada</span>}
        </div>
      </form>
    </div>
  )
}
