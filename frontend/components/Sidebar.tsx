"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { logout, getUser, AuthUser } from "@/lib/auth";
import {
  LayoutDashboard, Users, Server, DollarSign, Shield,
  FileText, BarChart2, PhoneCall, LogOut, Radio, Activity, TrendingUp
} from "lucide-react";

import { Layers } from "lucide-react";

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
    <aside className="w-56 min-h-screen bg-[var(--color-card)] border-r border-[var(--color-border)]
                      flex flex-col fixed left-0 top-0">
      <div className="px-6 py-5 border-b border-[var(--color-border)]">
        <span className="text-brand-500 font-bold text-lg tracking-tight">Kapla</span><span className="text-white font-bold text-lg tracking-tight">Billing</span>
      </div>

      <nav className="flex-1 py-4 overflow-y-auto">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = path.startsWith(href);
          return (
            <Link key={href} href={href}
              className={`flex items-center gap-3 px-6 py-2.5 text-sm transition-colors
                ${active
                  ? "bg-brand-600/20 text-brand-400 border-r-2 border-brand-500"
                  : "text-[var(--color-text-2)] hover:text-[var(--color-text)] hover:bg-white/5"
                }`}>
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="px-6 py-4 border-t border-[var(--color-border)]">
        <p className="text-sm text-[var(--color-text)] font-medium truncate">{user?.name}</p>
        <p className="text-xs text-[var(--color-text-2)] mb-3 capitalize">{user?.role}</p>
        <button onClick={logout}
          className="flex items-center gap-2 text-xs text-[var(--color-muted)]
                     hover:text-danger transition-colors">
          <LogOut size={14} /> Cerrar sesión
        </button>
      </div>
    </aside>
  );
}
