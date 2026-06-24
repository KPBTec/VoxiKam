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
  localStorage.setItem("kaplabilling_token", token);
  localStorage.setItem("kaplabilling_user", JSON.stringify(user));
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("kaplabilling_user");
  return raw ? JSON.parse(raw) : null;
}

export function logout() {
  localStorage.removeItem("kaplabilling_token");
  localStorage.removeItem("kaplabilling_user");
  window.location.href = "/login";
}
