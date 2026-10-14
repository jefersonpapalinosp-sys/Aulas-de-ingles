import { defineConfig } from '@playwright/test'

// Sem E2E_BASE_URL e sem stack Docker: não pode atingir a base de estudo.
export default defineConfig({
  testDir: './queue-tests',
  workers: 1,
  timeout: 30_000,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5197', browserName: 'chromium', serviceWorkers: 'block' },
  webServer: {
    command: '../frontend/node_modules/.bin/vite --config ../frontend/vite.queue-test.config.ts',
    url: 'http://127.0.0.1:5197/test-fixtures/offline-queue.html',
    reuseExistingServer: false,
  },
})
