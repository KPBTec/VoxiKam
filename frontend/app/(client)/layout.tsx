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
    <div className="flex min-h-screen">
      <Sidebar role="client" />
      <main className="ml-56 flex-1 p-8 overflow-auto">{children}</main>
    </div>
  );
}
