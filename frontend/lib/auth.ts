"use client";

export type ThemeId = "bronce" | "papel" | "fosforo" | "vidrio";
export const THEMES: { id: ThemeId; label: string; swatch: string }[] = [
  { id: "bronce",  label: "Bronce",  swatch: "#dd8b3d" },
  { id: "papel",   label: "Papel",   swatch: "#c7bc9d" },
  { id: "fosforo", label: "Fósforo", swatch: "#33cc66" },
  { id: "vidrio",  label: "Vidrio",  swatch: "#a8a8ad" },
];

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
  // Preferencia visual — persistida en users.ui_theme (por cuenta, no por
  // navegador). "bronce" = default, coincide con no tener el atributo seteado.
  ui_theme?: ThemeId;
}

// Aplica el tema al <html> + lo cachea en localStorage aparte del objeto
// user completo — se lee de forma síncrona en <head> (ver layout.tsx) antes
// de que React hidrate, para no mostrar un flash del tema por defecto.
export function applyTheme(theme: ThemeId | string | undefined) {
  if (typeof document === "undefined") return;
  const t = theme || "bronce";
  if (t === "bronce") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem("voxikam_theme", t);
}

export function saveAuth(token: string, user: AuthUser) {
  localStorage.setItem("voxikam_token", token);
  localStorage.setItem("voxikam_user", JSON.stringify(user));
  applyTheme(user.ui_theme);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("voxikam_user");
  return raw ? JSON.parse(raw) : null;
}

export function logout() {
  localStorage.removeItem("voxikam_token");
  localStorage.removeItem("voxikam_user");
  localStorage.removeItem("voxikam_theme");
  document.documentElement.removeAttribute("data-theme");
  window.location.href = "/login";
}
