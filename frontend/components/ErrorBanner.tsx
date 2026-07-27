// El bloque `bg-red-900/30 border-red-700 text-red-300` se repetía literal,
// carácter por carácter, en 11+ páginas del portal cliente — sobre --color-danger.
export function ErrorBanner({ children }: { children: React.ReactNode }) {
  if (!children) return null
  return (
    <div className="bg-danger/10 border border-danger/40 text-danger text-sm rounded-lg px-4 py-3">
      {children}
    </div>
  )
}
