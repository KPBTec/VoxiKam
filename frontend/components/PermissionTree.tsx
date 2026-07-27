// VoxiKam — SIP Class 4 Billing & Monitoring Platform
// Copyright (c) 2026 KPBTec
// By KPBTec · https://github.com/KPBTec
// © 2026 – Todos los derechos reservados.

export interface PermissionResource {
  resource_key: string
  parent_key: string | null
  label: string
  sort_order: number
  default_visible: boolean
}

interface ToggleRowProps { label: string; on: boolean; onToggle: () => void; sub?: boolean }

function ToggleRow({ label, on, onToggle, sub = false }: ToggleRowProps) {
  return (
    <div className={`flex items-center justify-between py-1 ${sub ? 'pl-6' : ''}`}>
      <span className={`text-sm ${sub ? 'text-[var(--color-text-2)]' : ''}`}>{label}</span>
      <button type="button" onClick={onToggle}
        className={`focus-ring relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${on ? 'bg-brand-600' : 'bg-[var(--color-card-2)]'}`}>
        <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${on ? 'translate-x-5' : 'translate-x-0.5'}`} />
      </button>
    </div>
  )
}

/**
 * Árbol de permisos genérico — usado tanto en /profiles (editor de perfil)
 * como en customers/[id]/page.tsx (override por cliente sin perfil). Un
 * resource CON hijos se renderiza como encabezado de grupo sin switch propio
 * (agrupa visualmente, no es un permiso real — ej. "Resumen" agrupando
 * "KPIs"/"Últimas llamadas"); un resource SIN hijos es una fila togglable.
 * `value` son overrides explícitos — lo no presente cae a default_visible.
 */
export function PermissionTree({
  resources, value, onChange, sectionFilter,
}: {
  resources: PermissionResource[]
  value: Record<string, boolean>
  onChange: (key: string, val: boolean) => void
  sectionFilter?: (r: PermissionResource) => boolean
}) {
  const all = sectionFilter ? resources.filter(sectionFilter) : resources
  const roots = all.filter(r => !r.parent_key).sort((a, b) => a.sort_order - b.sort_order)
  // Ojo: filtra sobre `all` (ya filtrado por sectionFilter), no sobre
  // `resources` — si un hijo no matchea el sectionFilter de su padre (ej.
  // resource_key mal prefijado) no debe colarse en la sección equivocada.
  const childrenOf = (key: string) => all.filter(r => r.parent_key === key).sort((a, b) => a.sort_order - b.sort_order)
  const isOn = (r: PermissionResource) => value[r.resource_key] ?? r.default_visible

  return (
    <div className="space-y-0.5">
      {roots.map(r => {
        const kids = childrenOf(r.resource_key)
        return (
          <div key={r.resource_key}>
            {kids.length > 0 ? (
              <p className="text-sm font-medium text-[var(--color-text)] pt-2 first:pt-0">{r.label}</p>
            ) : (
              <ToggleRow label={r.label} on={isOn(r)} onToggle={() => onChange(r.resource_key, !isOn(r))} />
            )}
            {kids.map(c => (
              <ToggleRow key={c.resource_key} sub label={c.label} on={isOn(c)}
                onToggle={() => onChange(c.resource_key, !isOn(c))} />
            ))}
          </div>
        )
      })}
    </div>
  )
}
