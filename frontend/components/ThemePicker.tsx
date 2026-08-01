"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getUser, applyTheme, THEMES, ThemeId } from "@/lib/auth";

/** Selector de tema — 4 swatches compactos en el footer de la sidebar.
 * Cambia al instante (applyTheme) y guarda en users.ui_theme vía API; si la
 * llamada falla, el tema visual ya cambió igual (se reintentará en el
 * próximo cambio o login — no vale la pena bloquear la UI por esto). */
export function ThemePicker() {
  const [current, setCurrent] = useState<string>("bronce");

  useEffect(() => {
    setCurrent(getUser()?.ui_theme || localStorage.getItem("voxikam_theme") || "bronce");
  }, []);

  async function choose(id: ThemeId) {
    if (id === current) return;
    setCurrent(id);
    applyTheme(id);
    const u = getUser();
    if (u) {
      u.ui_theme = id;
      localStorage.setItem("voxikam_user", JSON.stringify(u));
    }
    try {
      await apiFetch("/auth/me/theme", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme: id }),
      });
    } catch {
      // El tema ya se aplicó localmente — un fallo de red acá no debe
      // interrumpir nada, solo significa que no quedó guardado del lado
      // servidor (se reintenta solo en el próximo cambio de tema).
    }
  }

  return (
    <div className="px-3 pb-2.5">
      <div
        className="text-[10px] font-mono uppercase tracking-widest mb-2"
        style={{ color: "var(--color-muted)" }}
      >
        Apariencia
      </div>
      <div className="flex gap-2">
        {THEMES.map((t) => (
          <button
            key={t.id}
            type="button"
            title={t.label}
            aria-label={`Tema ${t.label}`}
            onClick={() => choose(t.id)}
            className="w-6 h-6 rounded-full transition-transform hover:scale-110 cursor-pointer"
            style={{
              background: t.swatch,
              border: `2px solid ${current === t.id ? "var(--color-text)" : "transparent"}`,
              boxShadow: "0 0 0 1px var(--color-border)",
            }}
          />
        ))}
      </div>
    </div>
  );
}
