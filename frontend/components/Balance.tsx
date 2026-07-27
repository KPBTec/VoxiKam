// Antes cada pantalla coloreaba el balance a mano, inconsistente entre sí:
// /my/overview lo mostraba en morado (sin token, sin importar el signo),
// la tabla de reseller/customers no lo coloreaba aunque su propio panel de
// detalle sí, y la ficha de cliente admin tenía el ternario repetido dos
// veces con clases Tailwind crudas. Un solo lugar: <=0 es --color-danger,
// > 0 es --color-success — siempre font-mono, es dinero.
export function Balance({
  amount, currency = 'S/.', className = '',
}: {
  amount: number | string
  currency?: string
  className?: string
}) {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount
  const cls = (Number.isFinite(n) ? n : 0) <= 0 ? 'text-danger' : 'text-success'
  return (
    <span className={`font-mono ${cls} ${className}`}>
      {currency} {(Number.isFinite(n) ? n : 0).toFixed(2)}
    </span>
  )
}
