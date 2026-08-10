'use client'

/**
 * Re-auditoría v2.56.0: patrón repetido en 9 archivos — `<tr onClick={...}>`
 * como único mecanismo para abrir un detalle/editor, sin `tabIndex`,
 * `role="button"` ni `onKeyDown`. Un `<tr>` no es focuseable por teclado ni
 * entra en el orden de Tab, así que un usuario sin mouse quedaba totalmente
 * bloqueado en esas pantallas — gap distinto al de los 46 aria-labels ya
 * corregidos en v2.56.0 (que cubrió botones de ícono, no filas de tabla).
 */
export function ClickableRow({
  onActivate,
  disabled,
  className,
  children,
  ...rest
}: {
  onActivate: () => void
  disabled?: boolean
} & Omit<React.HTMLAttributes<HTMLTableRowElement>, 'onClick' | 'onKeyDown'>) {
  if (disabled) {
    return <tr className={className} {...rest}>{children}</tr>
  }
  return (
    <tr
      role="button"
      tabIndex={0}
      onClick={onActivate}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onActivate()
        }
      }}
      className={className}
      {...rest}
    >
      {children}
    </tr>
  )
}
