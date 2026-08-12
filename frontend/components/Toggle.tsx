// VoxiKam — SIP Class 4 Billing & Monitoring Platform
// Copyright (c) 2026 KPBTec
// By KPBTec · https://github.com/KPBTec
// © 2026 – Todos los derechos reservados.

interface ToggleProps {
  checked: boolean
  onChange: () => void
  disabled?: boolean
  label?: string
  className?: string
}

// El círculo necesita una posición base explícita (left-0.5) — sin ella,
// el navegador decide su posición de arranque por su cuenta (depende del
// padding/box-model default del <button>), y el translate-x-4 del estado
// "encendido" termina empujándolo fuera del track en vez de quedar
// centrado con el mismo margen que el estado "apagado".
export function Toggle({ checked, onChange, disabled, label, className = '' }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onChange}
      disabled={disabled}
      className={`focus-ring relative w-9 h-5 rounded-full transition-colors flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed ${checked ? 'bg-brand-600' : 'bg-zinc-700'} ${className}`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${checked ? 'translate-x-4' : 'translate-x-0'}`}
      />
    </button>
  )
}
