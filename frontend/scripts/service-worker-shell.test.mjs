import assert from 'node:assert/strict'
import { createHash, webcrypto } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'

const html = '<!doctype html><title>Current release</title>'
function worker() {
  const handlers = new Map(), stores = new Map(), calls = []
  let online = true, content = html, cacheControl = 'public', quota = false
  const key = request => typeof request === 'string' ? request : request.url
  const caches = {
    open: async name => {
      if (!stores.has(name)) stores.set(name, new Map())
      const entries = stores.get(name)
      return {
        keys: async () => [...entries.keys()].map(url => new Request(url)),
        match: async request => entries.get(key(request))?.clone(),
        put: async (request, response) => {
          if (quota) throw new Error('QuotaExceededError')
          entries.set(key(request), response.clone())
        },
        delete: async request => entries.delete(key(request)),
      }
    },
    keys: async () => [...stores.keys()], delete: async name => stores.delete(name),
  }
  const template = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')
    .replace('__AULAS_RELEASE__', 'aaaaaaaaaaaaaaaa')
    .replace("'__AULAS_ASSETS__'", '[]').replace("'__AULAS_ENTRY__'", '[]')
    .replace('__AULAS_HTML_HASH__', createHash('sha256').update(html).digest('hex'))
  runInNewContext(template, { Request, Response, URL, Uint8Array, crypto: webcrypto,
    caches, AbortController, setTimeout, clearTimeout,
    self: { location: { origin: 'https://synthetic.invalid' }, addEventListener: (name, handler) => handlers.set(name, handler) },
    fetch: async (url, options) => {
      calls.push({ url, options })
      if (!online) throw new Error('offline')
      return new Response(content, { headers: { 'Content-Type': 'text/html', 'Cache-Control': cacheControl } })
    },
  })
  return {
    stores, calls,
    offline: () => { online = false }, otherRelease: () => { content = '<title>Other release</title>' },
    private: () => { cacheControl = 'private, no-store' }, full: () => { quota = true },
    navigate: () => new Promise((resolve, reject) => handlers.get('fetch')({
      request: { url: 'https://synthetic.invalid/listening/hotel?sessao=123', method: 'GET', destination: 'document', mode: 'navigate' },
      respondWith: promise => Promise.resolve(promise).then(resolve, reject),
    })),
  }
}

test('recupera shell ausente online e reabre offline sem persistir URL pessoal', async () => {
  const app = worker()
  assert.equal(await (await app.navigate()).text(), html)
  assert.equal(app.calls[0].options.credentials, 'omit')
  assert.deepEqual([...app.stores.values()].flatMap(store => [...store.keys()]), ['https://synthetic.invalid/'])
  app.offline()
  assert.equal(await (await app.navigate()).text(), html)
  assert.equal(app.calls.length, 1)
})

test('não mistura HTML de outra release com o worker instalado', async () => {
  const app = worker(); app.otherRelease()
  assert.equal(await (await app.navigate()).text(), '<title>Other release</title>')
  assert.equal([...app.stores.values()][0].size, 0)
  app.offline()
  await assert.rejects(app.navigate(), /offline/)
})

test('resposta privada e quota nunca produzem falsa cópia offline', async () => {
  for (const configure of ['private', 'full']) {
    const app = worker(); app[configure]()
    assert.equal(await (await app.navigate()).text(), html)
    assert.equal([...app.stores.values()][0].size, 0)
    app.offline()
    await assert.rejects(app.navigate(), /offline/)
  }
})
