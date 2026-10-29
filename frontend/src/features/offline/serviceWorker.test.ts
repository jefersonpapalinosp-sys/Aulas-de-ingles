import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, runInContext } from 'node:vm'
import { webcrypto } from 'node:crypto'
import { describe, expect, it, vi } from 'vitest'

const origin = 'https://aulas.example'
const version = '0123456789abcdef'
const template = readFileSync(resolve(process.cwd(), 'public/sw.js'), 'utf8')
const lesson = `${origin}/api/courses/voa-level-1/lessons/31`
const json = (text = '{"title":"Public lesson"}', headers: Record<string, string> = {}) => new Response(text, {
  headers: { 'Content-Type': 'application/json', 'X-Aulas-Offline': 'public-text-v1', ...headers },
})

class MemoryCache {
  entries = new Map<string, Response>()
  fail = false
  put(key: Request, response: Response) {
    if (this.fail) return Promise.reject(new Error('QuotaExceededError'))
    this.entries.set(key.url, response.clone())
    return Promise.resolve()
  }
  match(key: Request) { return Promise.resolve(this.entries.get(key.url)?.clone()) }
  keys() { return Promise.resolve([...this.entries.keys()].map((url) => new Request(url))) }
  delete(key: Request) { return Promise.resolve(this.entries.delete(key.url)) }
}

function worker() {
  const storage = new Map<string, MemoryCache>()
  const caches = {
    open: (name: string) => {
      if (!storage.has(name)) storage.set(name, new MemoryCache())
      return Promise.resolve(storage.get(name)!)
    },
    keys: () => Promise.resolve([...storage.keys()]),
    delete: (name: string) => Promise.resolve(storage.delete(name)),
  }
  // Eventos e funções rodam o worker real; apenas a plataforma de cache/rede é simulada.
  const listeners: Record<string, (event: unknown) => void> = {}
  const fetch = vi.fn<typeof globalThis.fetch>().mockRejectedValue(new Error('offline'))
  const self = { location: { origin }, clients: { claim: vi.fn() }, skipWaiting: vi.fn(),
    addEventListener: (type: string, handler: (event: unknown) => void) => { listeners[type] = handler } }
  const context = createContext({ self, caches, fetch, Request, Response, URL, Uint8Array,
    AbortController, setTimeout, clearTimeout, crypto: webcrypto, Date })
  runInContext(template.replace('__AULAS_RELEASE__', version)
    .replace("'__AULAS_ASSETS__'", JSON.stringify(['/assets/main.js', '/assets/lesson.js']))
    .replace("'__AULAS_ENTRY__'", JSON.stringify(['/assets/main.js'])), context)
  const evaluate = <T,>(code: string): T => runInContext(code, context) as T
  const store = evaluate<(kind: string, url: string, response: Response) => Promise<boolean>>('store')
  const cached = evaluate<(kind: string, url: string) => Promise<Response | undefined>>('cached')
  const dispatch = (url: string, options: { method?: string; mode?: string; destination?: string } = {}) => {
    let promise: Promise<Response> | undefined
    listeners.fetch!({ request: { url, method: 'GET', mode: 'cors', destination: '', ...options },
      respondWith: (value: Promise<Response>) => { promise = value } })
    return promise
  }
  return { storage, caches, fetch, self, evaluate, store, cached, dispatch, listeners }
}

describe('service worker: política executável', () => {
  it('guarda texto público anônimo e devolve offline, sem tokens ou headers pessoais', async () => {
    const w = worker()
    w.fetch.mockResolvedValueOnce(json())
    expect((await w.dispatch(lesson))?.status).toBe(200)
    expect(w.fetch).toHaveBeenCalledWith(lesson, expect.objectContaining({ credentials: 'omit', cache: 'no-store' }) as unknown)
    const response = await w.dispatch(lesson)
    expect(response?.headers.get('X-Aulas-Offline-Source')).toBe('cache')
    expect(await response?.json()).toEqual({ title: 'Public lesson' })
    const keys = await (await w.caches.open(`aulas-pwa-${version}-text`)).keys()
    expect(keys[0]?.headers.get('Authorization')).toBeNull()
    expect(keys[0]?.headers.get('Cookie')).toBeNull()
  })

  it.each<Record<string, string>>([
    { 'Cache-Control': 'private, no-store' }, { Vary: 'Cookie' }, { Vary: 'Authorization' },
    { 'X-Aulas-Offline': '' }, { 'Content-Type': 'text/html' },
  ])('recusa opt-in inválido e política privada: %j', async (headers) => {
    const w = worker()
    w.fetch.mockResolvedValueOnce(json('secret', headers))
    await w.dispatch(lesson)
    expect(await w.cached('text', lesson)).toBeUndefined()
  })

  it.each([
    ['/api/me', {}], ['/api/courses/voa-level-1/lessons/31/study-session', {}],
    ['/api/media/1', {}], ['/api/courses/voa-level-1/lessons/31', { method: 'POST' }],
    ['/api/lessons?token=secret', {}], ['/assets/main.js', { destination: 'audio' }],
    ['/assets/main.js', { destination: 'video' }], ['/not-in-manifest.js', { destination: 'script' }],
  ])('não intercepta %s %j', (path, options) => {
    expect(worker().dispatch(`${origin}${path}`, options)).toBeUndefined()
  })

  it('não intercepta mídia externa nem retorna HTML para API privada', () => {
    const w = worker()
    expect(w.dispatch('https://voa.example/audio.mp3')).toBeUndefined()
    expect(w.dispatch(`${origin}/api/me`, { mode: 'navigate' })).toBeUndefined()
  })

  it('retorna erro explícito para texto nunca visitado', async () => {
    const response = await worker().dispatch(lesson)
    expect(response?.status).toBe(503)
    expect(await response?.text()).toContain('Texto indisponível offline')
  })

  it('expira texto e limita quantidade, bytes e tamanho individual com escritas concorrentes', async () => {
    const w = worker()
    w.evaluate('LIMITS.text.count = 2; LIMITS.text.bytes = 10; LIMITS.text.item = 8')
    await Promise.all([1, 2, 3].map((n) => w.store('text', `${lesson}?lesson=${n}`, json('1234'))))
    const cache = await w.caches.open(`aulas-pwa-${version}-text`)
    expect((await cache.keys()).length).toBe(2)
    await w.store('text', lesson, json('12345678'))
    expect((await cache.keys()).length).toBe(1)
    expect(await w.store('text', `${lesson}?lesson=4`, json('123456789'))).toBe(false)
    const response = cache.entries.get(lesson)!
    response.headers.set('X-Aulas-Cached-At', String(Date.now() - 8 * 86400000))
    expect(await w.cached('text', lesson)).toBeUndefined()
  })

  it('falha de cota não derruba resposta online válida', async () => {
    const w = worker()
    ;(await w.caches.open(`aulas-pwa-${version}-text`)).fail = true
    w.fetch.mockResolvedValueOnce(json())
    expect(await (await w.dispatch(lesson))?.json()).toEqual({ title: 'Public lesson' })
    expect(w.evaluate('cacheUnavailable')).toBe(true)
  })

  it('5xx permite fallback, mas 404 remove cópia antiga', async () => {
    const w = worker()
    await w.store('text', lesson, json())
    w.fetch.mockResolvedValueOnce(new Response('', { status: 503 }))
    expect((await w.dispatch(lesson))?.status).toBe(200)
    w.fetch.mockResolvedValueOnce(new Response('', { status: 404 }))
    expect((await w.dispatch(lesson))?.status).toBe(404)
    expect(await w.cached('text', lesson)).toBeUndefined()
  })

  it('mantém shell único para todas as rotas sem criar entradas de navegação', async () => {
    const w = worker()
    await w.store('shell', '/', new Response('app', { headers: { 'Content-Type': 'text/html' } }))
    for (const path of ['/inicio', '/caderno', '/cursos/voa-level-1/aulas/31']) {
      expect(await (await w.dispatch(`${origin}${path}`, { mode: 'navigate' }))?.text()).toBe('app')
    }
    expect((await (await w.caches.open(`aulas-pwa-${version}-shell`)).keys()).length).toBe(1)
  })

  it('serve manifesto e ícone pré-carregados também sem rede', async () => {
    const w = worker()
    await w.store('shell', '/icon.svg', new Response('<svg/>'))
    await w.store('shell', '/manifest.webmanifest', json('{}'))
    expect(await (await w.dispatch(`${origin}/icon.svg`, { destination: 'image' }))?.text()).toBe('<svg/>')
    expect(await (await w.dispatch(`${origin}/manifest.webmanifest`))?.json()).toEqual({})
    expect(w.fetch).not.toHaveBeenCalled()
  })

  it('falha de instalação preserva release anterior e não força ativação', async () => {
    const w = worker()
    await w.caches.open('aulas-pwa-aaaaaaaaaaaaaaaa-shell')
    let pending: Promise<void> | undefined
    w.listeners.install!({ waitUntil: (p: Promise<void>) => { pending = p } })
    await expect(pending).rejects.toThrow('offline')
    expect(await w.caches.keys()).toEqual(['aulas-pwa-aaaaaaaaaaaaaaaa-shell'])
    expect(w.self.skipWaiting).not.toHaveBeenCalled()
  })

  it('ativação limpa só caches conhecidos de versões anteriores', async () => {
    const w = worker()
    for (const name of ['aulas-v21-1-text', 'aulas-pwa-aaaaaaaaaaaaaaaa-text', 'aulas-other-app', `aulas-pwa-${version}-shell`]) await w.caches.open(name)
    let pending: Promise<void> | undefined
    w.listeners.activate!({ waitUntil: (p: Promise<void>) => { pending = p } })
    await pending
    expect(await w.caches.keys()).toEqual(['aulas-other-app', `aulas-pwa-${version}-shell`])
    expect(w.self.skipWaiting).not.toHaveBeenCalled()
  })

  it('limpeza confirmada remove somente texto, não shell, assets ou outro cache', async () => {
    const w = worker()
    await w.store('text', lesson, json())
    await w.caches.open(`aulas-pwa-${version}-static`)
    await w.caches.open('other-app')
    const postMessage = vi.fn()
    let pending: Promise<void> | undefined
    w.listeners.message!({ source: { url: origin }, ports: [{ postMessage }],
      data: { type: 'PWA_CLEAR_TEXT', lessonPath: new URL(lesson).pathname },
      waitUntil: (p: Promise<void>) => { pending = p } })
    await pending
    expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({ count: 0, lesson: false }) as unknown)
    expect(await w.caches.keys()).toContain('other-app')
    expect(await w.caches.keys()).toContain(`aulas-pwa-${version}-static`)
  })
})
