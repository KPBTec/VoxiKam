"use client";
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getUser, AuthUser } from "@/lib/auth";
import { Sidebar } from "@/components/Sidebar";

const MODULE_MAP: Partial<Record<string, keyof AuthUser>> = {
  "/my/calls":       "show_calls",
  "/my/quality":     "show_quality",
  "/my/reports":     "show_reports",
  "/my/invoices":    "show_invoices",
  "/my/trunk-guide": "show_trunk_guide",
};

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const router  = useRouter();
  const path    = usePathname();

  useEffect(() => {
    const user = getUser();
    if (!user) { router.replace("/login"); return; }
    if (user.role !== "client") return;

    const moduleKey = MODULE_MAP[path];
    if (moduleKey && user[moduleKey] === false) {
      router.replace("/my/overview");
    }
  }, [router, path]);

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex flex-1">
        <Sidebar role="client" />
        <main className="ml-56 flex-1 p-8 overflow-auto">{children}</main>
      </div>
      <footer className="ml-56 px-8 py-3 border-t border-[var(--color-border)] flex items-center justify-between">
        <span className="text-xs text-[var(--color-text-2)] opacity-40">VoxiKam · SIP Class 4</span>
        <span className="text-xs text-[var(--color-text-2)] opacity-40">KPBTec · Knowledge, Protection &amp; Business Technology</span>
      </footer>
    </div>
  );
}
