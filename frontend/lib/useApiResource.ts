'use client'
import { useCallback, useEffect, useState } from 'react'
import { apiGet, getErrorMessage } from '@/lib/api'

/**
 * Auditoría v2.55 (workflow multi-agente): el patrón
 * `useState + useState + useState + useEffect(() => apiGet(...).then(setX)
 * .catch(...).finally(...))` está repetido a mano en casi todas las páginas
 * admin/cliente. Este hook lo centraliza — es SETUP, no una migración forzada:
 * las páginas existentes siguen funcionando igual sin tocarlas; una página
 * nueva (o una que se toque por otro motivo) puede adoptarlo así:
 *
 *   const { data: carriers, loading, error, reload } = useApiResource<Carrier[]>('/admin/carriers')
 *
 * Re-fetchea automáticamente cuando `path` cambia — cubre el caso de un
 * filtro en la URL (ej: `/admin/carriers?include_reseller=${x}`) sin necesitar
 * un array de deps aparte.
 */
export function useApiResource<T>(path: string, fallbackErrorMsg?: string) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reload = useCallback(() => {
    setLoading(true)
    setError('')
    return apiGet<T>(path)
      .then(d => { setData(d); return d })
      .catch((e: unknown) => {
        setError(getErrorMessage(e, fallbackErrorMsg ?? `Error cargando ${path}`))
        throw e
      })
      .finally(() => setLoading(false))
  }, [path, fallbackErrorMsg])

  useEffect(() => {
    reload().catch(() => {}) // el error ya quedó en `error` — no hace falta un unhandled rejection
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload])

  return { data, loading, error, reload, setData, setError }
}
