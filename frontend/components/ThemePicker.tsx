"use client";
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { getUser, applyTheme, THEMES, ThemeId } from "@/lib/auth";

/** Lista de temas — vive dentro del grupo colapsable "Apariencia" de la
 * sidebar (ver Sidebar.tsx). Cambia al instante (applyTheme) y guarda en
 * users.ui_theme vía API; si la llamada falla, el tema visual ya cambió
 * igual (se reintentará en el próximo cambio o login — no vale la pena
 * bloquear la UI por esto). */
export function ThemePicker() {
  const [current, setCurrent] = useState<string>("bronce");

  useEffect(() => {
    // Resuelve la preferencia guardada (cuenta > localStorage > default) y la
    // re-aplica acá, no solo para decidir el check visible. Sin esto: si el
    // script anti-flash del layout (que solo lee localStorage) y la
    // preferencia real de la cuenta quedan desincronizados (otro dispositivo,
    // cache borrada), la página seguía pintada con el tema viejo mientras el
    // picker ya mostraba el check correcto — el chequeo y lo renderizado
    // podían quedar desincronizados sin que nada los volviera a alinear.
    const resolved = getUser()?.ui_theme || localStorage.getItem("voxikam_theme") || "bronce";
    setCurrent(resolved);
    applyTheme(resolved);
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
    <>
      {THEMES.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => choose(t.id)}
          className={`w-full flex items-center gap-2.5 px-4 py-2 text-[13px] rounded-lg transition-all cursor-pointer
            ${current === t.id ? "font-semibold" : "font-medium hover:bg-white/5"}`}
          style={current === t.id ? {
            background: "rgba(221,139,61,.12)",
            color: "var(--color-brand-400)",
          } : {
            color: "var(--color-text-2)",
          }}
        >
          <span
            className="w-3 h-3 rounded-full flex-shrink-0"
            style={{ background: t.swatch, boxShadow: "0 0 0 1px var(--color-border)" }}
          />
          {t.label}
          {current === t.id && <Check size={13} style={{ marginLeft: "auto", flexShrink: 0 }} />}
        </button>
      ))}
    </>
  );
}
