"use client";

export interface AuthUser {
  name: string;
  role: "admin" | "client";
  customer_id: number | null;
  is_reseller?: boolean;
  // Árbol de permisos granular (resource_key -> visible) — reemplaza los
  // show_* sueltos de antes. Ver db/schema.sql (permission_resources) y
  // backend/auth.py::resolve_permissions(). Se resuelve una sola vez al
  // hacer login y se cachea acá — si un admin cambia un permiso a mitad de
  // sesión, el cliente lo ve recién en su próximo login (mismo criterio de
  // siempre, no es nuevo de este cambio).
  permissions?: Record<string, boolean>;
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
