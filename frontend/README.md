# frontend/

Next.js 15 con `output: 'standalone'`. Corre como servicio `voxikam-frontend` en `127.0.0.1:3000` detrás de Nginx.

## Stack

- **Next.js 15** + **React 19** + TypeScript
- **Tailwind CSS v4** con `@theme` tokens (dark design system)
- **jose** para decode de JWT en cliente
- `lucide-react` para íconos, `clsx` para classnames

## Estructura de carpetas

`app/(admin)/` y `app/(client)/my/` crecieron mucho desde que se escribió esto por primera vez —
son ~30 y ~15 páginas respectivamente hoy (perfiles, grupos de carriers, pricelists, seguridad/IPs,
webhooks, disconnect-policies, áreas, usuarios, auditoría, sistema, trazas, calidad ASR, alertas,
routing-sim, traffic-sampling, external-sync, billing-recalc, resellers, y el panel reseller propio
bajo `my/reseller/*`). Para el listado exacto, `ls "app/(admin)/"` / `ls "app/(client)/my/"`
directo, o la tabla de rutas backend en `../CLAUDE.md` (cada página admin tiene su router
homónimo). Convenciones que sí se mantienen estables:

```
app/
  page.tsx              ← root redirect por rol (no UI)
  layout.tsx            ← RootLayout: metadata + globals.css
  globals.css           ← @theme tokens: --color-surface, --color-card, --color-brand-*, etc.
  (auth)/login/         ← página de login (no sidebar)
  (admin)/layout.tsx    ← guard: no admin → /login. Cada subcarpeta = 1 página del panel admin
  (client)/layout.tsx   ← guard: no auth → /login; módulo sin permiso → /my/overview
  (client)/my/reseller/ ← panel de reseller (solo visible si customers.is_reseller=1)
components/
  Sidebar.tsx           ← adminNavTop (fijo) + adminNavGroups (colapsables, persistidos en
                           localStorage) — clientNav filtrado por permisos resueltos en login
  ClickableRow.tsx      ← <tr> accesible por teclado (role=button + tabIndex + onKeyDown)
  Modal.tsx             ← diálogo con Escape-to-close + focus trap
  StatusBadge.tsx       ← pills de estado sobre tokens semánticos (variant helpers por dominio)
  PermissionTree.tsx    ← editor del árbol granular de permisos (profiles/ y customers/[id])
lib/
  api.ts                ← apiFetch, apiGet, apiPost, apiPut, apiDelete, apiUpload
  auth.ts               ← saveAuth, getUser, logout (localStorage: voxikam_token/voxikam_user)
```

## Auth flow en el cliente

1. Login → `POST /api/auth/login` → recibe `{access_token, role, name, customer_id, permissions, ...}`
2. `saveAuth()` guarda token en `localStorage.voxikam_token` y user en `localStorage.voxikam_user`
   (incluye los permisos ya resueltos — el frontend no vuelve a pedirlos hasta el próximo login)
3. Redirect a `/dashboard` (admin) o `/my/overview` (client)
4. Cada layout guard lee `getUser()` en `useEffect` — si no hay user, redirect a `/login`
5. `apiFetch` lee `localStorage.voxikam_token` y lo agrega como `Authorization: Bearer`
6. Si el backend devuelve 401, `apiFetch` redirige automáticamente a `/login`

## Calls a la API

```typescript
import { apiGet, apiPost, apiFetch } from '@/lib/api'

// GET con query params
const data = await apiGet('/admin/cdrs/list?limit=50&offset=0')

// POST JSON
const r = await apiPost('/admin/customers', { name: 'Acme', email: '...' })

// Fetch raw (para form-data, streams, etc.)
const res = await apiFetch('/auth/login', { method: 'POST', body: formData })
```

`BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api"` — en producción esta var NO se setea (ver `templates/frontend.env.j2`), así que siempre cae a `/api` relativo. Nginx proxea `/api/` al backend en el mismo origen — funciona con cualquier dominio/IP/puerto sin reconstruir. Antes sí se horneaba una URL absoluta acá; se sacó tras un incidente real: acceder por un dominio distinto al que estaba seteado en el build rompía el frontend por completo (fetch cross-origin, excepción de cliente sin manejar).

## Design tokens (globals.css)

```css
--color-surface:  #0f172a   /* fondo global */
--color-card:     #1e293b   /* cards y paneles */
--color-border:   #334155   /* bordes */
--color-muted:    #64748b   /* texto secundario */
--color-text:     #f1f5f9   /* texto principal */
--color-brand-*   /* ámbar — NO azul/cian (compartido con VoxiDet, familia Voxi) */
--color-success/warning/danger
```

Usar `bg-[var(--color-card)]` o las clases de Tailwind: `bg-brand-600`, `text-brand-500`.

## Build y producción

```bash
npm install --include=optional   # --include=optional requerido por @tailwindcss/oxide (Node ≥ 20)
npm run build
# Standalone output en .next/standalone/server.js
# Estáticos copiados manualmente por deploy.sh:
cp -r .next/static   .next/standalone/.next/static
cp -r public         .next/standalone/public
```

**Importante:** Next.js standalone NO copia los estáticos. Sin ese cp, el CSS y JS no se sirven.

## Variables de entorno

`templates/frontend.env.j2` → `frontend/.env.local` durante deploy.sh (PASO 8), antes del build (PASO 10) — hoy solo trae `NEXT_PUBLIC_PLATFORM_NAME`/`NEXT_PUBLIC_SBC_HOST`/`NEXT_PUBLIC_SBC_PORT`. `NEXT_PUBLIC_API_URL` no se define (ver arriba).

## Logs

```bash
journalctl -u voxikam-frontend -n 50 -f
```

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
