"use client";

export interface AuthUser {
  name: string;
  role: "admin" | "client";
  customer_id: number | null;
  show_calls?: boolean;
  show_quality?: boolean;
  show_reports?: boolean;
  show_invoices?: boolean;
  show_trunk_guide?: boolean;
}

export function saveAuth(token: string, user: AuthUser) {
  localStorage.setItem("voxikam_token", token);
  localStorage.setItem("voxikam_user", JSON.stringify(user));
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("voxikam_user");
  return raw ? JSON.parse(raw) : null;
}

export function logout() {
  localStorage.removeItem("voxikam_token");
  localStorage.removeItem("voxikam_user");
  window.location.href = "/login";
}
