import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

/** Harness descartável: nunca herda o proxy da aplicação ou sua API real. */
export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  optimizeDeps: { include: ['react', 'react-dom/client', 'react/jsx-runtime'] },
  // HMR é infraestrutura de desenvolvimento, não recuperação do produto.
  // Não deixar otimização a frio provocar reload durante a asserção do teste.
  server: { host: '127.0.0.1', port: 5197, strictPort: true, hmr: false },
  plugins: [{
    name: 'deny-real-api',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.startsWith('/api/')) {
          res.writeHead(503, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ detail: 'API bloqueada no harness de fila.' }))
        } else next()
      })
    },
  }],
})
