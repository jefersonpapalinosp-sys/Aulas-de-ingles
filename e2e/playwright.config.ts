import { defineConfig, devices } from '@playwright/test'
import { assertTarget } from './safety.mjs'

/**
 * Bundle buildado + nginx + API sem reload, mas banco e voz exclusivos de E2E.
 * O setup verifica containers, volumes e identidade real antes de criar contas.
 * E2E_BASE_URL não é uma saída para apontar os testes a desenvolvimento/produção.
 */
const baseURL = assertTarget(process.env.E2E_BASE_URL)

export default defineConfig({
  testDir: './testes',
  globalSetup: './global-setup.ts',
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
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chrome', use: { ...devices['Pixel 5'] } },
    {
      name: 'firefox-sprint41',
      testMatch: /sprint41-accessibility\.spec\.ts/,
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit-sprint41',
      testMatch: /sprint41-accessibility\.spec\.ts/,
      use: { ...devices['Desktop Safari'] },
    },
  ],
})
