import { test, expect } from '@playwright/test';

/**
 * Smoke test de login — ver playwright.config.ts para por qué no depende de
 * un backend/DB real. Objetivo: detectar que la página de login se rompió
 * (build roto, campo faltante, manejo de errores roto) sin necesitar
 * levantar infraestructura.
 */
test.describe('Login', () => {
  test('renderiza el form con campos accesibles', async ({ page }) => {
    await page.goto('/login');

    await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Contraseña')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible();
  });

  test('bloquea el submit vacío por validación HTML5, sin llamar a la API', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: 'Ingresar' }).click();

    // Los campos marcados `required` bloquean el submit del lado del
    // navegador — el form nunca llega a disparar el fetch, así que seguimos
    // en /login, no en /dashboard, y sin el mensaje de error del catch.
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByText('Credenciales incorrectas')).not.toBeVisible();
  });

  test('credenciales contra un backend inexistente muestra un error visible, no cuelga la página', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill('admin@example.com');
    await page.getByLabel('Contraseña').fill('cualquier-cosa');
    await page.getByRole('button', { name: 'Ingresar' }).click();

    // Sin backend real en este entorno (ni proxy /api configurado en
    // next.config), /api/auth/login lo resuelve el propio Next.js dev
    // server con un 404 — res.ok da false SIN que el fetch tire excepción,
    // así que el código toma la rama "Credenciales incorrectas", no el
    // catch de "Error de conexión". Lo que este test realmente prueba: la
    // página no cuelga ni rompe, sigue en /login con un mensaje visible.
    await expect(page.getByText('Credenciales incorrectas')).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });
});
