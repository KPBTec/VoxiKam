interface LogoProps {
  size?: "sm" | "md" | "lg";
  variant?: "full" | "icon";
}

// logo.svg = horizontal (icono + wordmark + tagline), ratio ~360:82
const fullWidths  = { sm: 170, md: 230, lg: 300 };
// logo-icon.svg = solo el círculo K, cuadrado
const iconWidths  = { sm: 36,  md: 48,  lg: 64  };

export function Logo({ size = "md", variant = "full" }: LogoProps) {
  if (variant === "icon") {
    const s = iconWidths[size];
    return (
      <img src="/logo-icon.svg" alt="VoxiKam" width={s} height={s}
        style={{ flexShrink: 0 }} />
    );
  }

  return (
    <img src="/logo.svg" alt="VoxiKam" width={fullWidths[size]}
      style={{ display: "block", flexShrink: 0 }} />
  );
}
