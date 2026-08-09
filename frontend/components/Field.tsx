'use client'
import { useId } from 'react'

/**
 * Auditoría v2.55 (workflow multi-agente): ningún <input> del panel tenía
 * <label htmlFor> conectado a su id (ni aria-label) — el label era solo un
 * elemento visualmente adyacente, sin asociación programática. Un lector de
 * pantalla anuncia el input sin nombre, y hacer click en el texto del label
 * no enfoca el campo. Este componente es la pieza compartida para arrancar
 * a corregir eso — no reemplaza los ~13 inputs sueltos de un saque, se migra
 * página por página (ver users/page.tsx y carriers/page.tsx como piloto).
 */
type FieldProps = {
  label: string
  error?: string
  hint?: string
  containerClassName?: string
} & React.InputHTMLAttributes<HTMLInputElement>

export function Field({ label, error, hint, containerClassName, id, className, ...inputProps }: FieldProps) {
  const generatedId = useId()
  const fieldId = id ?? generatedId
  const hintId = hint ? `${fieldId}-hint` : undefined
  const errorId = error ? `${fieldId}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined

  return (
    <div className={containerClassName}>
      <label htmlFor={fieldId} className="block text-xs text-[var(--color-text-2)] mb-1">
        {label}
      </label>
      <input
        id={fieldId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={
          className ??
          'w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-500'
        }
        {...inputProps}
      />
      {hint && !error && (
        <p id={hintId} className="mt-1 text-xs text-[var(--color-muted)]">{hint}</p>
      )}
      {error && (
        <p id={errorId} className="mt-1 text-xs text-danger">{error}</p>
      )}
    </div>
  )
}
