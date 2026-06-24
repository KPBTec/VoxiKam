"use client";

interface GaugeProps {
  value: number;
  max: number;
  label: string;
  sub?: string;
  unit?: "%" | "Mbps" | "GB";
  size?: number;
}

function arcColor(pct: number): string {
  if (pct < 0.6) return "#22c55e";
  if (pct < 0.8) return "#f59e0b";
  return "#ef4444";
}

function fmtValue(value: number, unit: GaugeProps["unit"]): string {
  if (unit === "%")    return `${Math.round(value)}%`;
  if (unit === "GB")   return `${value.toFixed(1)}G`;
  if (unit === "Mbps") {
    if (value >= 1000) return `${(value / 1000).toFixed(1)}Gb`;
    if (value >= 1)    return `${value.toFixed(1)}M`;
    return `${(value * 1000).toFixed(0)}K`;
  }
  return String(value);
}

export function Gauge({ value, max, label, sub, unit = "%", size = 140 }: GaugeProps) {
  // Clamp pct to avoid degenerate SVG arcs
  const pct   = Math.min(0.999, Math.max(0.001, value / Math.max(max, 0.001)));
  const W     = size;
  const cx    = W / 2;
  const cy    = W * 0.58;
  const r     = W * 0.40;
  const sw    = W * 0.09;
  const H     = cy + sw / 2 + 20;
  const color = arcColor(pct);

  // SVG arc convention: 0°=right, angles increase CW (screen), y-down
  // Background: left(180°) → right(360°) through top(270°) — large-arc=1, sweep=1
  const lx = cx - r, ly = cy;
  const rx = cx + r, ry = cy;

  // Foreground endpoint at angle = 180° + pct*180°
  const θ  = (180 + pct * 180) * (Math.PI / 180);
  const fx = cx + r * Math.cos(θ);
  const fy = cy + r * Math.sin(θ);

  const glow = `drop-shadow(0 0 5px ${color}99)`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H}>
      {/* Track */}
      <path
        d={`M ${lx} ${ly} A ${r} ${r} 0 1 1 ${rx} ${ry}`}
        fill="none" stroke="#27272a" strokeWidth={sw} strokeLinecap="round"
      />
      {/* Fill */}
      <path
        d={`M ${lx} ${ly} A ${r} ${r} 0 0 1 ${fx} ${fy}`}
        fill="none" stroke={color} strokeWidth={sw} strokeLinecap="round"
        style={{ filter: glow }}
      />
      {/* Value */}
      <text
        x={cx} y={cy - r * 0.08}
        textAnchor="middle" dominantBaseline="middle"
        fill="white" fontSize={W * 0.16} fontWeight="700" fontFamily="monospace"
      >
        {fmtValue(value, unit)}
      </text>
      {/* Sub-label (e.g. "3.9 / 8.0 GB") */}
      {sub && (
        <text
          x={cx} y={cy + r * 0.22}
          textAnchor="middle" dominantBaseline="middle"
          fill="#71717a" fontSize={W * 0.09}
        >
          {sub}
        </text>
      )}
      {/* Min / Max ticks */}
      <text x={lx + 2} y={ly + sw / 2 + 10} textAnchor="start"  fill="#52525b" fontSize={W * 0.08}>0</text>
      <text x={rx - 2} y={ry + sw / 2 + 10} textAnchor="end"    fill="#52525b" fontSize={W * 0.08}>
        {unit === "Mbps" ? fmtValue(max, "Mbps") : `${max}${unit}`}
      </text>
      {/* Label */}
      <text
        x={cx} y={H - 2}
        textAnchor="middle" dominantBaseline="auto"
        fill="#a1a1aa" fontSize={W * 0.1} fontWeight="600"
      >
        {label}
      </text>
    </svg>
  );
}

/** Auto-scale network max to the next "round" ceiling above the current value */
export function netMax(mbps: number): number {
  if (mbps < 1)    return 1;
  if (mbps < 10)   return 10;
  if (mbps < 100)  return 100;
  if (mbps < 1000) return 1000;
  return 10000;
}
