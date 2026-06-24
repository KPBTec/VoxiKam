# frontend/

Next.js 15 con `output: 'standalone'`. Corre como servicio `sip-frontend` en `127.0.0.1:3000` detrás de Nginx.

## Stack

- **Next.js 15** + **React 19** + TypeScript
- **Tailwind CSS v4** con `@theme` tokens (dark design system)
- **jose** para decode de JWT en cliente
- `lucide-react` para íconos, `clsx` para classnames

## Estructura de carpetas

```
app/
  page.tsx              ← root redirect por rol (no UI)
  layout.tsx            ← RootLayout: metadata + globals.css
  globals.css           ← @theme tokens: --color-surface, --color-card, --color-brand-*, etc.
  (auth)/login/         ← página de login (no sidebar)
  (admin)/              ← layout con guard admin + sidebar
    dashboard/          ← KPIs + active calls (poll 30s)
    live/               ← llamadas por cliente en tiempo real (poll 10s)
    customers/          ← listado clientes con link a detalle
    customers/[id]/     ← detalle: IPs autorizadas (add/del), carriers, balance, edición
    carriers/           ← CRUD carriers
    rates/              ← planes tarifarios + tarifas por destino
    cdrs/               ← visor CDRs con filtros y paginación
    reports/            ← resúmenes día/mes agrupados por cliente o carrier (botón Generar)
    invoices/           ← generar factura, marcar pagada, descargar PDF
    firewall/           ← reglas IP ALLOW/DENY/JAIL
  (client)/my/          ← layout con guard cliente + sidebar
    overview/           ← 4 KPIs + active calls + últimas 5 calls (poll 30s)
    calls/              ← historial CDR, máx 200 registros, con aviso si capped
    invoices/           ← facturas del cliente + descargar PDF
    trunk-guide/        ← config Asterisk autogenerada con datos del trunk
components/
  Sidebar.tsx           ← sidebar role-aware (9 items admin, 4 items cliente)
  ui/                   ← componentes reutilizables (Card, Badge, etc.)
lib/
  api.ts                ← apiFetch, apiGet, apiPost, apiPut, apiDelete
  auth.ts               ← saveAuth, getUser, logout (localStorage)
```

## Auth flow en el cliente

1. Login → `POST /api/auth/login` → recibe `{access_token, role, name, customer_id}`
2. `saveAuth()` guarda token en `localStorage.sip_token` y user en `localStorage.sip_user`
3. Redirect a `/dashboard` (admin) o `/my/overview` (client)
4. Cada layout guard lee `getUser()` en `useEffect` — si no hay user, redirect a `/login`
5. `apiFetch` lee `localStorage.sip_token` y lo agrega como `Authorization: Bearer`
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

`BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api"` — en producción se bake en el build con el valor de `.env.local`.

## Design tokens (globals.css)

```css
--color-surface:  #0f172a   /* fondo global */
--color-card:     #1e293b   /* cards y paneles */
--color-border:   #334155   /* bordes */
--color-muted:    #64748b   /* texto secundario */
--color-text:     #f1f5f9   /* texto principal */
--color-brand-*   /* sky-500 palette */
--color-success/warning/danger
```

Usar `bg-[var(--color-card)]` o las clases de Tailwind: `bg-brand-600`, `text-brand-500`.

## Build y producción

```bash
npm install --include=optional   # --include=optional requerido por @tailwindcss/oxide (Node ≥ 20)
npm run build
# Standalone output en .next/standalone/server.js
# Estáticos copiados manualmente por install.sh:
cp -r .next/static   .next/standalone/.next/static
cp -r public         .next/standalone/public
```

**Importante:** Next.js standalone NO copia los estáticos. Sin ese cp, el CSS y JS no se sirven.

## Variables de entorno

```
NEXT_PUBLIC_API_URL=http://<domain>:<port>/api
```

Se genera en `templates/frontend.env.j2` → `frontend/.env.local` durante install.sh (PASO 8), antes del build (PASO 10), para que se bake en el bundle.

## Logs

```bash
journalctl -u sip-frontend -n 50 -f
```

---

> © 2026 [KPBTec](https://github.com/KPBTec) · Ver [Licencia y Autoría](../AUTHORS.md)
