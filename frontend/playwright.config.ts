import { defineConfig, devices } from '@playwright/test';

/**
 * Auditoría v2.55 (workflow multi-agente): "Setup: Playwright + smoke test
 * de login" — sin ningún test end-to-end, un build verde (typecheck + next
 * build en CI) no garantiza que el login realmente RENDERICE ni que el
 * manejo de errores funcione; solo que el código compila. Este smoke test
 * no depende de un backend/DB real (no hay ninguno en CI) — cubre lo que sí
 * se puede verificar sin infraestructura: que el form de login renderiza
 * con sus campos accesibles, que el submit vacío lo bloquea la validación
 * HTML5, y que un fetch que falla (backend inexistente en este entorno)
 * muestra el mensaje de error esperado en vez de romper la página.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3100',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL ? undefined : {
    command: 'npm run dev -- -p 3100',
    url: 'http://127.0.0.1:3100',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
