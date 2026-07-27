// Agrupa las filas de /admin/live::by_customer (una fila por techprefix —
// principal + cada prefijo de campaña) en una sola fila por CLIENTE real.
// Compartido entre live/page.tsx y dashboard/page.tsx — antes vivía solo en
// live/page.tsx, dashboard consumía by_customer crudo y mostraba el mismo
// cliente repetido una vez por cada prefijo de campaña activo.
export function groupByCustomer(rows: any[]) {
  const map = new Map<string, any[]>()
  for (const r of rows) {
    const key = r.customer_id != null ? `c${r.customer_id}` : `pfx${r.prefijo}`
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(r)
  }
  return Array.from(map.values()).map(rows => ({
    customer_id:   rows[0].customer_id,
    customer_name: rows[0].customer_name,
    active_calls:  rows.reduce((a, r) => a + (r.active_calls || 0), 0),
    timbrando:     rows.reduce((a, r) => a + (r.timbrando || 0), 0),
    total:         rows.reduce((a, r) => a + (r.total || 0), 0),
    rows,
  })).sort((a, b) => b.active_calls - a.active_calls)
}
