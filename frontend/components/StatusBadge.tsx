// Voxi Design System — pill de estado sobre los tokens semánticos reales
// (--color-success/warning/danger/info-*), no la paleta Tailwind cruda.
// Antes de esto, cada página reimplementaba su propio mapa de colores a mano
// (customers/resellers/users/profiles/cdrs/traces) — 7+ copias casi
// idénticas, con colores huérfanos (morado, naranja) que no existen en
// ningún token del sistema.
export type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'muted' | 'brand'

// Tailwind v4 autogenera utilidades directo de cada --color-* del @theme
// (confirmado real: hover:text-danger ya funciona hoy en firewall/page.tsx)
// — se usa la forma bg-success/text-danger/etc., NUNCA bg-[var(--color-*)],
// para que quede consistente con el resto del código que ya usa brand-600
// como clase, no como arbitrary value.
const FILLED_CLS: Record<BadgeVariant, string> = {
  success: 'bg-success/15 text-success',
  warning: 'bg-warning/15 text-warning',
  danger:  'bg-danger/15 text-danger',
  info:    'bg-info-100 text-info-400',
  muted:   'bg-[var(--color-border)] text-[var(--color-muted)]',
  brand:   'bg-brand-500/15 text-brand-400',
}

const BORDERED_CLS: Record<BadgeVariant, string> = {
  success: 'text-success bg-success/10 border-success/30',
  warning: 'text-warning bg-warning/10 border-warning/30',
  danger:  'text-danger bg-danger/10 border-danger/30',
  info:    'text-info-400 bg-info-100/40 border-info-300/30',
  muted:   'text-[var(--color-text-2)] bg-[var(--color-card-2)] border-[var(--color-border-2)]/40',
  brand:   'text-brand-400 bg-brand-500/10 border-brand-400/30',
}

const DOT_CLS: Record<BadgeVariant, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger:  'bg-danger',
  info:    'bg-info-400',
  muted:   'bg-[var(--color-muted)]',
  brand:   'bg-brand-400',
}

export function StatusBadge({
  variant, children, dot = false, bordered = false, mono = false, rounded = 'full', tight = false, className = '', title,
}: {
  variant: BadgeVariant
  children: React.ReactNode
  dot?: boolean
  bordered?: boolean
  mono?: boolean
  /** 'full' = pill (default, la mayoría de los casos) — 'md' = chip rectangular
   * (ej. traces.tsx, donde el badge original no era una pill). No se resuelve
   * vía className porque Tailwind no garantiza que una clase repetida en el
   * className del caller le gane a la del componente en especificidad/orden. */
  rounded?: 'full' | 'md'
  /** padding más ajustado (px-1.5 en vez de px-2) — mismo motivo que `rounded`. */
  tight?: boolean
  className?: string
  title?: string
}) {
  const base = bordered
    ? `border ${BORDERED_CLS[variant]}`
    : FILLED_CLS[variant]
  return (
    <span title={title} className={`inline-flex items-center gap-1.5 ${tight ? 'px-1.5' : 'px-2'} py-0.5 ${rounded === 'full' ? 'rounded-full' : 'rounded'} text-xs font-medium ${base} ${mono ? 'font-mono' : ''} ${className}`}>
      {dot && <span className={`w-2 h-2 rounded-full ${DOT_CLS[variant]}`} />}
      {children}
    </span>
  )
}

/** Estado de customers/resellers (active/suspended/expired/deleted) — mismo
 * mapa que antes se repetía a mano en customers/resellers/[id]/page.tsx. */
export function customerStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case 'active':    return 'success'
    case 'suspended': return 'warning'
    case 'expired':   return 'danger'
    default:          return 'muted' // deleted / desconocido
  }
}

/** disposition de cdrs (ANSWERED/BUSY/CANCELLED/REJECTED/DIVERTED/etc).
 * El default original (antes de este componente) caía en rojo para
 * cualquier estado no reconocido explícitamente — "si no sé qué es,
 * alarmo". Acá se preserva esa señal: solo CANCELLED/NO ANSWER (los dos
 * casos neutrales reales) van a muted; cualquier otra cosa no listada
 * cae en danger, no en muted. */
export function callStateVariant(state: string): BadgeVariant {
  switch (state) {
    case 'COMPLETED':                    return 'success'
    case 'BUSY':                         return 'warning'
    case 'DIVERTED':                     return 'info'
    case 'REJECTED':                     return 'danger'
    case 'INTERRUMPIDA POR REINICIO':    return 'warning'
    case 'CANCELLED':                    return 'muted'
    case 'NO ANSWER':                    return 'muted'
    default:                             return 'danger' // estado desconocido — alarmar, no ocultar
  }
}

/** Código de respuesta SIP — mismo criterio usado en cdrs.py::sipBadge() y
 * traces.tsx::statusCls(), unificado acá. */
export function sipCodeVariant(code: number): BadgeVariant {
  if (code < 200) return 'warning'
  if (code < 300) return 'success'
  if (code < 400) return 'info'
  if (code < 500) return 'warning' // 4xx: --color-warning ya es ámbar/naranja, cubre el "naranja" que se usaba suelto
  return 'danger'
}

/** Estado de facturas (draft/sent/paid/overdue) — mismo mapa que se repetía
 * a mano en admin invoices/page.tsx y my/invoices/page.tsx. */
export function invoiceStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case 'paid':    return 'success'
    case 'sent':    return 'info'
    case 'overdue': return 'danger'
    default:        return 'muted' // draft / desconocido
  }
}

/** Método SIP sin código de respuesta todavía (traces.tsx) — BYE/CANCEL no
 * son "buenos ni malos", son neutrales; antes BYE usaba morado huérfano. */
export function sipMethodVariant(method: string | null): BadgeVariant {
  switch (method) {
    case 'INVITE': return 'brand'
    case 'BYE':    return 'info'
    case 'CANCEL': return 'warning'
    default:       return 'muted' // ACK / desconocido
  }
}

/** Estado de drafts de tarifas (draft/published/discarded) — antes
 * pricelists/page.tsx armaba estos colores a mano con text-yellow-400/
 * text-green-400 en vez de los tokens semánticos del resto del sistema. */
export function draftStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case 'draft':     return 'warning'
    case 'published': return 'success'
    default:          return 'muted' // discarded / desconocido
  }
}

/** Estado de carriers (active/inactive) — antes carriers/page.tsx y
 * carriers/[id]/page.tsx armaban este pill a mano con bg-green-x / bg-zinc-x. */
export function carrierStatusVariant(status: string): BadgeVariant {
  return status === 'active' ? 'success' : 'muted'
}
