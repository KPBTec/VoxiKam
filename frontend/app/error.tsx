'use client'

import { useEffect } from 'react'

// Antes de esto no existía NINGÚN error boundary en todo el frontend — un
// crash de React se veía como pantalla en blanco para el usuario, y el
// equipo nunca se enteraba (cero console.error, cero reporting). Reporta al
// backend (best-effort, fetch directo sin lib/api.ts — tiene que funcionar
// incluso con la sesión rota) y muestra una salida real en vez de blanco.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    fetch('/api/client-errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: error.message || 'Error desconocido',
        stack: error.stack || '',
        url: typeof window !== 'undefined' ? window.location.href : '',
      }),
    }).catch(() => {
      // Si esto falla no hay nada más que hacer — no re-lanzar dentro de un error boundary
    })
  }, [error])

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-surface)] px-4">
      <div className="max-w-md w-full text-center space-y-4">
        <p className="text-[var(--color-brand-500)] text-sm font-medium tracking-wide uppercase">
          VoxiKam
        </p>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">
          Algo salió mal en esta página
        </h1>
        <p className="text-sm text-[var(--color-text-2)]">
          El error ya quedó registrado. Podés intentar de nuevo o volver al inicio.
        </p>
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={reset}
            className="px-4 py-2 rounded-md bg-[var(--color-brand-500)] text-[var(--color-surface)] text-sm font-medium hover:bg-[var(--color-brand-400)] transition-colors"
          >
            Reintentar
          </button>
          <a
            href="/"
            className="px-4 py-2 rounded-md border border-[var(--color-border)] text-[var(--color-text)] text-sm font-medium hover:border-[var(--color-border-2)] transition-colors"
          >
            Volver al inicio
          </a>
        </div>
      </div>
    </div>
  )
}
