"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getUser } from "@/lib/auth";

export default function Root() {
  const router = useRouter();
  useEffect(() => {
    const user = getUser();
    if (!user) router.replace("/login");
    else if (user.role === "admin") router.replace("/dashboard");
    else router.replace("/my/overview");
  }, [router]);
  return null;
}
