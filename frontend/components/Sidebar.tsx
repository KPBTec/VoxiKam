"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { logout, getUser, AuthUser } from "@/lib/auth";
import {
  LayoutDashboard, Users, Server, DollarSign, Shield,
  FileText, BarChart2, PhoneCall, LogOut, Radio, TrendingUp,
  Layers, BellRing, UserCog, History, MapPin, DatabaseZap, Webhook, PhoneOff, Route, Gauge, FileStack,
  ChevronRight, Mail, Menu, X, Building2, Activity, Palette, KeyRound, ArrowLeftRight, Shuffle, PhoneIncoming, Hash,
  Network, Ban, ScrollText, RefreshCcw, ShieldCheck, Trash2,
} from "lucide-react";
import { Logo } from "@/components/Logo";

type NavItem = { href: string; label: string; icon: React.ElementType };

// path.startsWith(href) solo no alcanza cuando un href es prefijo literal de
// otro (ej: /my/reseller vs /my/reseller/customers) — exige un límite de "/"
// o coincidencia exacta, así "Reseller: Resumen" no queda marcado activo en
// sus propias subpáginas. Mismo resultado que antes para todo lo que no colisiona.
function isNavActive(path: string, href: string): boolean {
  return path === href || path.startsWith(href + "/");
}

// Dashboard/Live quedan siempre visibles arriba — son los que más se usan.
const adminNavTop: NavItem[] = [
  { href: "/dashboard",  label: "Dashboard",  icon: LayoutDashboard },
  { href: "/live",       label: "Live",        icon: Radio },
];

// El resto agrupado en secciones colapsables — la sidebar plana pasó de 4 a
// 22 items en una sola sesión (v2.9.0 → v2.23.0) y dejó de ser navegable.
const adminNavGroups: { label: string; items: NavItem[] }[] = [
  {
    label: "Clientes",
    items: [
      { href: "/customers",  label: "Clientes",    icon: Users },
      { href: "/resellers",  label: "Resellers",   icon: Building2 },
      { href: "/profiles",   label: "Perfiles",    icon: Layers },
      { href: "/users",      label: "Usuarios",    icon: UserCog },
    ],
  },
  {
    label: "Ruteo",
    items: [
      { href: "/carriers",             label: "Carriers",              icon: Server },
      { href: "/inbound",              label: "Entrante",              icon: PhoneIncoming },
      { href: "/carrier-groups",       label: "Grupos de ruteo",       icon: Shuffle },
      { href: "/routing-sim",          label: "Routing Sim",           icon: Route },
      { href: "/disconnect-policies",  label: "Disconnect Policies",   icon: PhoneOff },
    ],
  },
  {
    label: "Tarifas",
    items: [
      { href: "/rates",        label: "Tarifas",     icon: DollarSign },
      { href: "/prefixes",     label: "Prefijos",    icon: Hash },
      { href: "/area-groups",  label: "Áreas",       icon: MapPin },
      { href: "/pricelists",   label: "Pricelists",  icon: FileStack },
    ],
  },
  {
    label: "Seguridad",
    items: [
      { href: "/firewall",             label: "Firewall",         icon: Shield },
      { href: "/security/customer-ips", label: "IPs de clientes",  icon: Network },
      { href: "/security/fail2ban",     label: "Fail2ban",         icon: Ban },
      { href: "/audit",                 label: "Auditoría",        icon: History },
    ],
  },
  {
    label: "Tráfico",
    items: [
      { href: "/cdrs",    label: "CDRs",        icon: PhoneCall },
      { href: "/traces",  label: "Trazas SIP",  icon: ArrowLeftRight },
    ],
  },
  {
    label: "Reportes",
    items: [
      { href: "/reports",  label: "Consumos",      icon: BarChart2 },
      { href: "/areas",    label: "Por destino",   icon: MapPin },
      { href: "/quality",  label: "Calidad ASR",   icon: TrendingUp },
    ],
  },
  {
    label: "Facturación",
    items: [
      { href: "/invoices",            label: "Facturas",             icon: FileText },
      { href: "/invoice-template",    label: "Plantilla de factura", icon: Palette },
      { href: "/alerts/consumption",  label: "Alertas de balance",   icon: BellRing },
      { href: "/billing-recalc",      label: "Recalcular tarifas",   icon: RefreshCcw },
      { href: "/billing-reset",       label: "Reset facturación",    icon: Trash2 },
    ],
  },
  {
    label: "Sistema",
    items: [
      { href: "/system-health",     label: "Salud",              icon: Activity },
      { href: "/system/logs",       label: "Logs",               icon: ScrollText },
      { href: "/system/infra",      label: "Infraestructura",    icon: ShieldCheck },
      { href: "/external-sync",     label: "Sync externa",       icon: DatabaseZap },
      { href: "/mail-config",       label: "Correo",             icon: Mail },
      { href: "/traffic-sampling",  label: "Retención de datos", icon: Gauge },
      { href: "/webhooks",          label: "Webhooks",           icon: Webhook },
    ],
  },
];

// module = resource_key de permission_resources (db/schema.sql), no una
// columna de AuthUser — ver frontend/lib/auth.ts (AuthUser.permissions).
const clientNav: { href: string; label: string; icon: React.ElementType; module: string | null; resellerOnly?: boolean }[] = [
  { href: "/my/overview",    label: "Resumen",      icon: LayoutDashboard, module: null },
  { href: "/my/calls",       label: "Mis llamadas", icon: PhoneCall,       module: "calls" },
  { href: "/my/quality",     label: "Calidad ASR",  icon: TrendingUp,      module: "quality" },
  { href: "/my/reports",     label: "Reportes",     icon: BarChart2,       module: "reports" },
  { href: "/my/invoices",    label: "Facturas",     icon: FileText,        module: "invoices" },
  { href: "/my/trunk-guide", label: "Trunk Guide",  icon: Server,          module: "trunk_guide" },
  { href: "/my/carriers",    label: "Mis carriers", icon: Route,           module: "carriers" },
  { href: "/my/api-keys",    label: "API Keys",     icon: KeyRound,        module: "api_access" },
  { href: "/my/reseller",           label: "Reseller: Resumen", icon: Building2,  module: "reseller_dashboard", resellerOnly: true },
  { href: "/my/reseller/customers", label: "Sub-clientes",      icon: Users,      module: "reseller_customers", resellerOnly: true },
  { href: "/my/reseller/rates",     label: "Tarifas propias",   icon: DollarSign, module: "reseller_rates",     resellerOnly: true },
  { href: "/my/reseller/prefixes",  label: "Prefijos propios",  icon: Hash,       module: "reseller_rates",     resellerOnly: true },
  { href: "/my/reseller/carriers",  label: "Carriers propios",  icon: Route,      module: "reseller_carriers",  resellerOnly: true },
  { href: "/my/reseller/carrier-groups", label: "Grupos de ruteo", icon: Shuffle, module: "reseller_carriers",  resellerOnly: true },
  { href: "/my/reseller/billing-recalc", label: "Recalcular tarifas", icon: RefreshCcw, module: "reseller_customers", resellerOnly: true },
];

function NavLink({ href, label, icon: Icon, active, onNavigate }: NavItem & { active: boolean; onNavigate?: () => void }) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={`flex items-center gap-2.5 px-4 py-2.5 text-[13px] rounded-lg transition-all
        ${active ? "font-semibold" : "font-medium hover:bg-white/5"}`}
      style={active ? {
        background: "rgba(221,139,61,.12)",
        color: "var(--color-brand-400)",
        borderLeft: "2px solid var(--color-brand-500)",
      } : {
        color: "var(--color-text-2)",
        borderLeft: "2px solid transparent",
      }}
    >
      <Icon size={15} style={{ flexShrink: 0 }} />
      {label}
    </Link>
  );
}

/**
 * "Signal path": el grupo abierto queda unido por un borde/tinte ámbar continuo
 * de la cabecera a sus items (como una traza en un circuito) — así la jerarquía
 * grupo→página activa es obvia de un vistazo, sin depender solo del color del
 * texto. El punto (LED) en la cabecera se prende si el grupo tiene la página
 * activa adentro, AUNQUE esté colapsado porque el usuario abrió otro grupo a
 * propósito — nunca perdés de vista dónde estás parado realmente.
 */
function NavGroup({ group, isOpen, hasActive, path, onToggle, onNavigate }: {
  group: { label: string; items: NavItem[] };
  isOpen: boolean;
  hasActive: boolean;
  path: string;
  onToggle: () => void;
  onNavigate?: () => void;
}) {
  return (
    <div
      className="pt-1 rounded-lg transition-colors duration-200"
      style={{
        background: isOpen ? "rgba(221,139,61,.05)" : "transparent",
        borderLeft: isOpen ? "2px solid var(--color-brand-500)" : "2px solid transparent",
        marginLeft: "2px",
      }}
    >
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider transition-colors cursor-pointer"
        style={{ color: hasActive ? "var(--color-brand-400)" : "var(--color-muted)" }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0 transition-all"
          style={{
            background: hasActive ? "var(--color-brand-500)" : "transparent",
            boxShadow: hasActive ? "0 0 5px var(--color-brand-500)" : "none",
          }}
        />
        <span className="flex-1 text-left">{group.label}</span>
        <ChevronRight size={13} className="transition-transform duration-200" style={{ transform: isOpen ? "rotate(90deg)" : "rotate(0deg)" }} />
      </button>

      {/* Grid-rows en vez de mount/unmount condicional: la altura anima suave
          en vez de saltar de golpe cuando cambiás de grupo. */}
      <div
        className="grid transition-[grid-template-rows] duration-200 ease-out"
        style={{ gridTemplateRows: isOpen ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          <div className="space-y-0.5 pb-0.5">
            {group.items.map(item => (
              <NavLink key={item.href} {...item} active={isNavActive(path, item.href)} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function SidebarContent({ role, onNavigate }: { role: "admin" | "client"; onNavigate?: () => void }) {
  const path = usePathname();
  const user  = getUser();

  const activeGroupLabel = adminNavGroups.find(g => g.items.some(i => isNavActive(path, i.href)))?.label ?? null;

  // Acordeón: un solo grupo abierto a la vez, siempre sincronizado con la
  // página actual — así nunca queda ambiguo en qué sección estás, ni se van
  // acumulando grupos abiertos a medida que navegás por distintas páginas.
  const [openGroup, setOpenGroup] = useState<string | null>(activeGroupLabel);
  useEffect(() => { setOpenGroup(activeGroupLabel) }, [path]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleGroup(label: string) {
    setOpenGroup(prev => (prev === label ? null : label));
  }

  return (
    <>
      {/* Logo */}
      <div className="riveted px-4 py-3.5 border-b border-[var(--color-border)] flex items-center gap-3 flex-shrink-0">
        <Logo size="sm" variant="icon" />
        <div>
          <div className="nameplate text-[16px] leading-tight">
            <span style={{ color: "var(--color-brand-400)" }}>Voxi</span>
            <span style={{ color: "var(--color-text-2)" }}>Kam</span>
          </div>
          <div className="text-[10px] font-mono tracking-widest uppercase" style={{ color: "var(--color-muted)" }}>
            SIP Class 4
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto space-y-0.5 px-2">
        {role === "client" ? (
          clientNav
            .filter(item => (!item.module || user?.permissions?.[item.module] !== false) && (!item.resellerOnly || user?.is_reseller))
            .map(item => <NavLink key={item.href} {...item} active={isNavActive(path, item.href)} onNavigate={onNavigate} />)
        ) : (
          <>
            {adminNavTop.map(item => (
              <NavLink key={item.href} {...item} active={isNavActive(path, item.href)} onNavigate={onNavigate} />
            ))}

            {adminNavGroups.map(group => (
              <NavGroup
                key={group.label}
                group={group}
                path={path}
                isOpen={openGroup === group.label}
                hasActive={group.items.some(i => isNavActive(path, i.href))}
                onToggle={() => toggleGroup(group.label)}
                onNavigate={onNavigate}
              />
            ))}
          </>
        )}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-[var(--color-border)] flex-shrink-0">
        <div className="flex items-center gap-2.5 mb-3">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
            style={{
              background: "linear-gradient(135deg, var(--color-brand-600) 0%, var(--color-brand-500) 100%)",
              boxShadow: "0 0 10px rgba(221,139,61,.3)",
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
    </>
  );
}

const asideStyle: React.CSSProperties = {
  background: "var(--color-card)",
  borderRight: "1px solid var(--color-border)",
  backgroundImage: "linear-gradient(180deg, rgba(221,139,61,.04) 0%, transparent 35%)",
};

export function Sidebar({ role }: { role: "admin" | "client" }) {
  const path = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Cerrar el drawer mobile al navegar — sin esto queda tapando la página
  // recién abierta hasta que el usuario lo cierra a mano.
  useEffect(() => { setMobileOpen(false) }, [path]);

  return (
    <>
      {/* Barra superior — solo mobile/tablet angosto. En desktop (md+) no existe. */}
      <div
        className="md:hidden fixed top-0 left-0 right-0 h-14 flex items-center px-4 gap-3 z-30"
        style={{ background: "var(--color-card)", borderBottom: "1px solid var(--color-border)" }}
      >
        <button onClick={() => setMobileOpen(true)} aria-label="Abrir menú" className="p-1.5 -ml-1.5 text-[var(--color-text-2)] cursor-pointer">
          <Menu size={20} />
        </button>
        <Logo size="sm" variant="icon" />
        <span className="nameplate text-[16px]">
          <span style={{ color: "var(--color-brand-400)" }}>Voxi</span><span style={{ color: "var(--color-text-2)" }}>Kam</span>
        </span>
      </div>

      {/* Sidebar desktop — fija, siempre visible, nunca se superpone al contenido */}
      <aside className="hidden md:flex w-56 min-h-screen flex-col fixed left-0 top-0" style={asideStyle}>
        <SidebarContent role={role} />
      </aside>

      {/* Drawer mobile — overlay que no empuja ni tapa el contenido cuando está cerrado */}
      <div
        className={`md:hidden fixed inset-0 z-40 transition-opacity duration-200 ${mobileOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"}`}
        style={{ background: "rgba(0,0,0,.6)" }}
        onClick={() => setMobileOpen(false)}
      />
      <aside
        className={`md:hidden w-64 max-w-[80vw] min-h-screen flex flex-col fixed left-0 top-0 z-50 transition-transform duration-200 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}
        style={asideStyle}
      >
        <button
          onClick={() => setMobileOpen(false)}
          aria-label="Cerrar menú"
          className="absolute top-3.5 right-3 p-1.5 text-[var(--color-text-2)] cursor-pointer"
        >
          <X size={18} />
        </button>
        <SidebarContent role={role} onNavigate={() => setMobileOpen(false)} />
      </aside>
    </>
  );
}
