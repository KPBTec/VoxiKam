import { ButtonHTMLAttributes, ReactNode } from 'react'

// Auditoría UX/visual: el mismo string de clases (bg-brand-600 hover:bg-brand-500
// disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors)
// estaba copiado a mano en 13+ lugares, más 8 variantes casi idénticas — y varios
// de esos botones no tenían .focus-ring. Este componente no inventa un look
// nuevo: fija el que ya era mayoría, para que dejar de copiarlo a mano sea
// literalmente lo más fácil.

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost'
export type ButtonSize = 'sm' | 'md'

const VARIANT_CLS: Record<ButtonVariant, string> = {
  primary:   'bg-brand-600 hover:bg-brand-500 text-white',
  secondary: 'border border-[var(--color-border)] hover:border-brand-500 text-[var(--color-text)]',
  danger:    'bg-danger/15 border border-danger/40 text-danger hover:bg-danger/25',
  ghost:     'text-[var(--color-muted)] hover:text-[var(--color-text)]',
}

const SIZE_CLS: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
}

export function Button({
  variant = 'primary', size = 'md', icon, children, className = '', ...rest
}: {
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: ReactNode
  children?: ReactNode
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`focus-ring inline-flex items-center gap-1.5 font-medium rounded-lg transition-colors disabled:opacity-50 disabled:pointer-events-none ${VARIANT_CLS[variant]} ${SIZE_CLS[size]} ${className}`}
      {...rest}
    >
      {icon}
      {children}
    </button>
  )
}
