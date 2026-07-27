"use client";
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getUser } from "@/lib/auth";
import { Sidebar } from "@/components/Sidebar";

// resource_key de permission_resources (db/schema.sql) por ruta — solo para
// no mostrar un fetch fallido feo si alguien entra por URL directa a algo
// que tiene deshabilitado; la aplicación real del permiso vive en el
// backend (require_permission), esto es puro adorno de UX.
const MODULE_MAP: Record<string, string> = {
  "/my/calls":       "calls",
  "/my/quality":     "quality",
  "/my/reports":     "reports",
  "/my/invoices":    "invoices",
  "/my/trunk-guide": "trunk_guide",
  "/my/carriers":    "carriers",
};

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const router  = useRouter();
  const path    = usePathname();

  useEffect(() => {
    const user = getUser();
    if (!user) { router.replace("/login"); return; }
    if (user.role !== "client") return;

    const resourceKey = MODULE_MAP[path];
    if (resourceKey && user.permissions?.[resourceKey] === false) {
      router.replace("/my/overview");
      return;
    }

    // /my/reseller* no está en MODULE_MAP porque son 3 rutas, no una — el
    // backend ya rechaza con 403 (require_reseller), esto es solo para no
    // mostrar un fetch fallido feo si alguien entra por URL directa sin serlo.
    if (path.startsWith("/my/reseller") && !user.is_reseller) {
      router.replace("/my/overview");
    }
  }, [router, path]);

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex flex-1">
        <Sidebar role="client" />
        <main className="md:ml-56 flex-1 p-8 pt-20 md:pt-8 overflow-auto">{children}</main>
      </div>
      <footer className="md:ml-56 px-8 py-3 border-t border-[var(--color-border)] flex items-center justify-between text-xs text-[var(--color-text-2)] opacity-60">
        <span>VoxiKam · SIP Class 4</span>
        <span className="flex items-center gap-2.5">
          <span>KPBTec · Knowledge, Protection &amp; Business Technology</span>
          <span className="text-[0.68rem] px-2 py-0.5 rounded-full border border-[var(--color-border)]">
            v{process.env.NEXT_PUBLIC_VOXIKAM_VERSION}
          </span>
        </span>
      </footer>
    </div>
  );
}
