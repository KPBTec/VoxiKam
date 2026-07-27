'use client'

import { useEffect } from 'react'

// app/error.tsx no captura errores del propio layout raíz — Next.js exige
// este archivo aparte para ese caso, con <html>/<body> propios porque
// reemplaza todo el layout cuando se dispara.
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
        message: error.message || 'Error desconocido (root layout)',
        stack: error.stack || '',
        url: typeof window !== 'undefined' ? window.location.href : '',
      }),
    }).catch(() => {})
  }, [error])

  return (
    <html lang="es">
      <body style={{ background: '#070c16', color: '#e2e8f0', fontFamily: 'sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
          <div style={{ maxWidth: 420, textAlign: 'center' }}>
            <p style={{ color: '#dd8b3d', fontSize: '0.875rem', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              VoxiKam
            </p>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 600, margin: '0.75rem 0' }}>
              No se pudo cargar la plataforma
            </h1>
            <p style={{ fontSize: '0.875rem', color: '#6b87a8', marginBottom: '1.25rem' }}>
              El error ya quedó registrado.
            </p>
            <button
              onClick={reset}
              style={{ padding: '0.5rem 1rem', borderRadius: 6, background: '#dd8b3d', color: '#070c16', border: 'none', fontSize: '0.875rem', fontWeight: 500, cursor: 'pointer' }}
            >
              Reintentar
            </button>
          </div>
        </div>
      </body>
    </html>
  )
}
