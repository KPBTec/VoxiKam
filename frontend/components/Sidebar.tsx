"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { logout, getUser, AuthUser } from "@/lib/auth";
import {
  LayoutDashboard, Users, Server, DollarSign, Shield,
  FileText, BarChart2, PhoneCall, LogOut, Radio, Activity, TrendingUp,
  Layers,
} from "lucide-react";
import { Logo } from "@/components/Logo";

const adminNav = [
  { href: "/dashboard",  label: "Dashboard",  icon: LayoutDashboard },
  { href: "/live",       label: "Live",        icon: Radio },
  { href: "/customers",  label: "Clientes",    icon: Users },
  { href: "/profiles",   label: "Perfiles",    icon: Layers },
  { href: "/carriers",   label: "Carriers",    icon: Server },
  { href: "/rates",      label: "Tarifas",     icon: DollarSign },
  { href: "/cdrs",       label: "CDRs",        icon: PhoneCall },
  { href: "/traces",     label: "Trazas SIP",  icon: Activity },
  { href: "/quality",    label: "Calidad ASR", icon: TrendingUp },
  { href: "/reports",    label: "Reportes",    icon: BarChart2 },
  { href: "/invoices",   label: "Facturas",    icon: FileText },
  { href: "/firewall",   label: "Firewall",    icon: Shield },
];

const clientNav: { href: string; label: string; icon: React.ElementType; module: keyof AuthUser | null }[] = [
  { href: "/my/overview",    label: "Resumen",      icon: LayoutDashboard, module: null },
  { href: "/my/calls",       label: "Mis llamadas", icon: PhoneCall,       module: "show_calls" },
  { href: "/my/quality",     label: "Calidad ASR",  icon: TrendingUp,      module: "show_quality" },
  { href: "/my/reports",     label: "Reportes",     icon: BarChart2,       module: "show_reports" },
  { href: "/my/invoices",    label: "Facturas",     icon: FileText,        module: "show_invoices" },
  { href: "/my/trunk-guide", label: "Trunk Guide",  icon: Server,          module: "show_trunk_guide" },
];

export function Sidebar({ role }: { role: "admin" | "client" }) {
  const path = usePathname();
  const user  = getUser();
  const nav   = role === "admin"
    ? adminNav
    : clientNav.filter(item =>
        !item.module || user?.[item.module] !== false
      );

  return (
    <aside
      className="w-56 min-h-screen flex flex-col fixed left-0 top-0"
      style={{
        background: "var(--color-card)",
        borderRight: "1px solid var(--color-border)",
        backgroundImage: "linear-gradient(180deg, rgba(14,165,233,.04) 0%, transparent 35%)",
      }}
    >
      {/* Logo */}
      <div className="px-5 py-4 border-b border-[var(--color-border)]">
        <Logo size="sm" />
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto space-y-0.5 px-2">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 px-4 py-2.5 text-[13px] rounded-lg transition-all
                ${active
                  ? "font-semibold"
                  : "font-medium hover:bg-white/5"
                }`}
              style={active ? {
                background: "rgba(14,165,233,.12)",
                color: "var(--color-brand-400)",
                borderLeft: "2px solid var(--color-brand-500)",
              } : {
                color: "var(--color-text-2)",
              }}
            >
              <Icon size={15} style={{ flexShrink: 0 }} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-[var(--color-border)]">
        <div className="flex items-center gap-2.5 mb-3">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
            style={{
              background: "linear-gradient(135deg, var(--color-brand-600) 0%, var(--color-brand-500) 100%)",
              boxShadow: "0 0 10px rgba(14,165,233,.3)",
            }}
          >
            {user?.name?.[0]?.toUpperCase() ?? "U"}
          </div>
          <div className="min-w-0">
            <p className="text-[13px] font-semibold truncate" style={{ color: "var(--color-text)" }}>
              {user?.name}
            </p>
            <p className="text-[11px] capitalize" style={{ color: "var(--color-text-2)" }}>
              {user?.role}
            </p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-2 text-xs transition-colors cursor-pointer"
          style={{ color: "var(--color-muted)" }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--color-danger)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--color-muted)")}
        >
          <LogOut size={13} /> Cerrar sesión
        </button>
      </div>
    </aside>
  );
}
