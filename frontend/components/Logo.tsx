import React from "react";

interface LogoProps {
  size?: "sm" | "md" | "lg";
  variant?: "full" | "icon";
}

const sizes = {
  sm: { icon: 28, font: "text-base",  sub: "text-[10px]" },
  md: { icon: 36, font: "text-xl",    sub: "text-xs" },
  lg: { icon: 48, font: "text-3xl",   sub: "text-sm" },
};

export function Logo({ size = "md", variant = "full" }: LogoProps) {
  const s = sizes[size];

  const icon = (
    <svg
      width={s.icon}
      height={s.icon}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ flexShrink: 0 }}
    >
      <defs>
        <linearGradient id="kb-grad" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#0ea5e9" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>
        <linearGradient id="kb-glow" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#38bdf8" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.06" />
        </linearGradient>
      </defs>
      {/* background */}
      <rect width="40" height="40" rx="10" fill="url(#kb-grad)" />
      <rect width="40" height="40" rx="10" fill="url(#kb-glow)" />
      {/* K lettermark */}
      <path
        d="M11 10 L11 30 M11 20 L23 10 M11 20 L24 30"
        stroke="white"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* dot accent */}
      <circle cx="29" cy="10" r="2.5" fill="rgba(255,255,255,0.5)" />
    </svg>
  );

  if (variant === "icon") return icon;

  return (
    <div className="flex items-center gap-3" style={{ userSelect: "none" }}>
      {icon}
      <div>
        <div className={`${s.font} font-bold leading-tight tracking-tight`}>
          <span className="text-brand-400">Kapla</span>
          <span className="text-white">Billing</span>
        </div>
        <div className={`${s.sub} text-[var(--color-text-2)] tracking-widest uppercase font-medium`}>
          SIP Class 4/5
        </div>
      </div>
    </div>
  );
}
