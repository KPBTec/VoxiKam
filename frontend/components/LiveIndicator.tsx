// VoxiKam — SIP Class 4 Billing & Monitoring Platform
// Copyright (c) 2026 KPBTec
// By KPBTec · https://github.com/KPBTec
// © 2026 – Todos los derechos reservados.

interface LiveIndicatorProps {
  /** false = pausado/inactivo (punto apagado, sin pulso) */
  active?: boolean;
  label: string;
  /** true cuando el indicador va sobre un fondo sólido de color (ej. un botón-toggle
   * relleno) — el punto pasa a blanco para tener contraste, en vez del token success. */
  onColoredBg?: boolean;
  className?: string;
}

export function LiveIndicator({ active = true, label, onColoredBg = false, className = "" }: LiveIndicatorProps) {
  const dotColor = !active ? "bg-[var(--color-muted)]" : onColoredBg ? "bg-white" : "bg-success";
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <span className={`w-2 h-2 rounded-full ${dotColor} ${active ? "animate-pulse" : ""}`} />
      {label}
    </span>
  );
}
