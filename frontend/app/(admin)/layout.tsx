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
    <div className="flex min-h-screen">
      <Sidebar role="admin" />
      <main className="ml-56 flex-1 p-8 overflow-auto">{children}</main>
    </div>
  );
}
