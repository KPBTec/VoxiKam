"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getUser } from "@/lib/auth";
import { Sidebar } from "@/components/Sidebar";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  useEffect(() => {
    const user = getUser();
    if (!user) router.replace("/login");
    else if (user.role !== "admin") router.replace("/my/overview");
  }, [router]);

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex flex-1">
        <Sidebar role="admin" />
        <main className="ml-56 flex-1 p-8 overflow-auto">{children}</main>
      </div>
      <footer className="ml-56 px-8 py-3 border-t border-[var(--color-border)] flex items-center justify-between">
        <span className="text-xs text-[var(--color-text-2)] opacity-40">VoxiKam · SIP Class 4</span>
        <span className="text-xs text-[var(--color-text-2)] opacity-40">KPBTec · Knowledge, Protection &amp; Business Technology</span>
      </footer>
    </div>
  );
}
