import { HTMLAttributes, ReactNode } from 'react'

// Auditoría visual: `bg-[var(--color-card)] border border-[var(--color-border)]
// rounded-xl` (a veces rounded-lg) se repetía en ~90 lugares, cada uno con su
// propio padding a mano (p-5, p-4, p-6, px-5 py-4...) — tres ritmos de
// espaciado distintos en la misma app. `padded` cubre el caso más común
// (contenido suelto con padding uniforme); las tablas siguen armando su propio
// header/body porque tienen su propio ritmo (px-6 py-3 por celda).
export function Card({
  padded = false, className = '', children, ...rest
}: {
  padded?: boolean
  children?: ReactNode
} & HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl ${padded ? 'p-5' : ''} ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}
