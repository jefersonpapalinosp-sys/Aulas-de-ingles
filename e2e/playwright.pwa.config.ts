import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './pwa-tests', outputDir: './pwa-test-results', workers: 1, timeout: 30_000, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5196', browserName: 'chromium' },
  webServer: {
    command: 'node pwa-fixture.mjs', url: 'http://127.0.0.1:5196', reuseExistingServer: false,
  },
})
