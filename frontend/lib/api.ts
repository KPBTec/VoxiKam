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

export async function apiGet(path: string) {
  const r = await apiFetch(path);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail ?? `GET ${path} → ${r.status}`);
  }
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
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail ?? `DELETE ${path} → ${r.status}`);
  }
  return r.status === 204 ? null : r.json();
}

// multipart/form-data — no pasar Content-Type manual, el browser arma el boundary solo
export async function apiUpload(path: string, file: File, fieldName = "file") {
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
