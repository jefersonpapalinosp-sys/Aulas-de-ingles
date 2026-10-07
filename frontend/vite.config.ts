import react from '@vitejs/plugin-react'
// defineConfig vem do vitest/config (e não do vite) para que a chave `test`
// seja tipada — com o import do vite, tsc rejeita a configuração de teste.
import { defineConfig } from 'vitest/config'

// O browser nunca fala direto com a API: tudo passa por /api na mesma origem.
// Isso evita CORS em dev e deixa o caminho pronto para o cookie httpOnly da S3.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8010'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
