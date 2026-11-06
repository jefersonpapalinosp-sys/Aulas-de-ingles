// Servidor descartável: nenhum proxy, banco, .env, áudio ou conta real.
import { createServer } from 'node:http'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import ts from '../frontend/node_modules/typescript/lib/typescript.js'

const template = readFileSync(new URL('../frontend/public/sw.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const appUpdate = ts.transpileModule(
  readFileSync(new URL('../frontend/src/features/offline/appUpdate.ts', import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } },
).outputText
let release = 'aaaaaaaaaaaaaaaa'
let broken = false
const html = () => `<!doctype html><html><head><title>PWA sintético</title></head><body><p id="release">${release}</p><input id="draft" aria-label="Rascunho sintético"><script src="/assets/probe.js"></script></body></html>`
const server = createServer((request, response) => {
  response.setHeader('Cache-Control', 'no-cache')
  if (request.url === '/__test__/release' && request.method === 'POST') {
    const candidate = request.headers['x-test-release']
    if (typeof candidate !== 'string' || !/^[a-f0-9]{16}$/.test(candidate)) { response.writeHead(400).end(); return }
    release = candidate
    broken = request.headers['x-test-broken'] === '1'
    response.end('ok'); return
  }
  if (request.url?.startsWith('/app-update.js')) {
    response.setHeader('Content-Type', 'application/javascript')
    response.end(appUpdate); return
  }
  if (request.url === '/sw.js') {
    response.setHeader('Content-Type', 'application/javascript')
    const workerTemplate = release === 'aaaaaaaaaaaaaaaa'
      ? template.replace("  if (event.data?.type === 'SKIP_WAITING') {\n    event.waitUntil(self.skipWaiting())\n    return\n  }\n", '')
      : template
    response.end(workerTemplate.replace('__AULAS_RELEASE__', release)
      .replace("'__AULAS_ASSETS__'", '["/assets/probe.js"]')
      .replace("'__AULAS_ENTRY__'", '["/assets/probe.js"]')
      .replace('__AULAS_HTML_HASH__', createHash('sha256').update(broken ? 'wrong-release' : html()).digest('hex')))
    return
  }
  if (request.url === '/assets/probe.js') {
    response.setHeader('Content-Type', 'application/javascript')
    response.end('navigator.serviceWorker.register("/sw.js", {updateViaCache:"none"})'); return
  }
  if (request.url === '/manifest.webmanifest') {
    response.setHeader('Content-Type', 'application/manifest+json'); response.end('{}'); return
  }
  if (request.url === '/icon.svg') {
    response.setHeader('Content-Type', 'image/svg+xml'); response.end('<svg xmlns="http://www.w3.org/2000/svg"/>'); return
  }
  if (/^\/icon-(180|192|512)\.png$/.test(request.url ?? '')) {
    response.setHeader('Content-Type', 'image/png')
    response.end(readFileSync(new URL(`../frontend/public${request.url}`, import.meta.url))); return
  }
  if (request.url === '/api/lessons/31') {
    response.setHeader('Content-Type', 'application/json')
    response.setHeader('Cache-Control', 'public, max-age=0, must-revalidate')
    response.setHeader('X-Aulas-Offline', 'public-text-v1')
    response.end('{"title":"Synthetic lesson"}'); return
  }
  response.setHeader('Content-Type', 'text/html')
  response.end(html())
})
server.listen(5196, '127.0.0.1')
