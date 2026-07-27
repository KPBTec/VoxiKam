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
