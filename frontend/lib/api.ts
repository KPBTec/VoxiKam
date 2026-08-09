const BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export async function apiFetch(path: string, options: RequestInit = {}) {
  let token: string | null = null;
  if (typeof window !== "undefined") {
    token = localStorage.getItem("voxikam_token");
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("voxikam_token");
      window.location.href = "/login";
    }
  }

  return res;
}

// Auditoría v2.55: estas firmas devolvían Promise<any> — todo el response
// quedaba sin tipo en el caller (chequeo de forma solo "a ojo", sin ayuda del
// compilador). El <T = any> es puramente aditivo: los ~50+ call sites
// existentes sin especificar el genérico siguen infiriendo `any` exactamente
// igual que antes — cero cambio de comportamiento — y un caller nuevo (o uno
// migrado a propósito) puede escribir apiGet<Carrier[]>(...) y obtener el tipo real.
export async function apiGet<T = any>(path: string): Promise<T> {
  const r = await apiFetch(path);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail ?? `GET ${path} → ${r.status}`);
  }
  return r.json();
}

export async function apiPost<T = any>(path: string, body: unknown): Promise<T> {
  const r = await apiFetch(path, { method: "POST", body: JSON.stringify(body) });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail ?? `POST ${path} → ${r.status}`);
  }
  return r.json();
}

export async function apiPut<T = any>(path: string, body: unknown): Promise<T> {
  const r = await apiFetch(path, { method: "PUT", body: JSON.stringify(body) });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail ?? `PUT ${path} → ${r.status}`);
  }
  return r.json();
}

export async function apiDelete<T = any>(path: string): Promise<T | null> {
  const r = await apiFetch(path, { method: "DELETE" });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail ?? `DELETE ${path} → ${r.status}`);
  }
  return r.status === 204 ? null : r.json();
}

// multipart/form-data — no pasar Content-Type manual, el browser arma el boundary solo
export async function apiUpload<T = any>(path: string, file: File, fieldName = "file"): Promise<T> {
  const form = new FormData();
  form.append(fieldName, file);
  const token = typeof window !== "undefined" ? localStorage.getItem("voxikam_token") : null;
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    body: form,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `POST ${path} → ${res.status}`);
  }
  return res.json();
}

// Auditoría v2.55: el patrón `err instanceof Error ? err.message : 'fallback'`
// está repetido a mano en 13+ catch blocks (app/(admin)/areas/page.tsx,
// area-groups, prefixes, invoice-template, routing-sim...) — cada uno con su
// propio fallback. Este helper no reemplaza esos call sites (migrarlos es
// mecánico, no urgente), pero establece el punto único para escribirlo bien
// una sola vez: `err` de un catch es `unknown`, nunca asumir que es Error.
export function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}
