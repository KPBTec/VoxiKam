const BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export async function apiFetch(path: string, options: RequestInit = {}) {
  let token: string | null = null;
  if (typeof window !== "undefined") {
    token = localStorage.getItem("kaplabilling_token");
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
      localStorage.removeItem("kaplabilling_token");
      window.location.href = "/login";
    }
  }

  return res;
}

export async function apiGet(path: string) {
  const r = await apiFetch(path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

export async function apiPost(path: string, body: unknown) {
  const r = await apiFetch(path, { method: "POST", body: JSON.stringify(body) });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail ?? `POST ${path} → ${r.status}`);
  }
  return r.json();
}

export async function apiPut(path: string, body: unknown) {
  const r = await apiFetch(path, { method: "PUT", body: JSON.stringify(body) });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail ?? `PUT ${path} → ${r.status}`);
  }
  return r.json();
}

export async function apiDelete(path: string) {
  const r = await apiFetch(path, { method: "DELETE" });
  if (!r.ok) throw new Error(`DELETE ${path} → ${r.status}`);
  return r.status === 204 ? null : r.json();
}
