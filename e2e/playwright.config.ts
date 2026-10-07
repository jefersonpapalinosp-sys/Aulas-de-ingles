import { defineConfig, devices } from '@playwright/test'

/**
 * A suíte E2E aponta para o alvo via E2E_BASE_URL.
 *
 * O padrão é o compose de **produção** (5181), e não o de dev: o ponto do
 * E2E é exercitar o que vai rodar — bundle buildado atrás do nginx, API sem
 * reload. Para rodar contra o dev: E2E_BASE_URL=http://localhost:5180
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5181'

export default defineConfig({
  testDir: './testes',
  fullyParallel: false, // os testes compartilham o banco
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['html'], ['list']] : 'list',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
