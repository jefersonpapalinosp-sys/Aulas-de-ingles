// Substituídos pelo build; não registrar o template no servidor de desenvolvimento.
const VERSION = '__AULAS_RELEASE__'
const ASSETS = '__AULAS_ASSETS__'
const ENTRY = '__AULAS_ENTRY__'
const HTML_HASH = '__AULAS_HTML_HASH__'
const DAY = 86400000
const LIMITS = {
  shell: { count: 3, bytes: 1048576, item: 524288, ttl: 30 * DAY },
  static: { count: 64, bytes: 8388608, item: 2097152, ttl: 30 * DAY },
  text: { count: 120, bytes: 8388608, item: 524288, ttl: 7 * DAY },
}
const cacheName = (kind) => `aulas-pwa-${VERSION}-${kind}`
const ownCache = (name) => /^aulas-pwa-[a-f0-9]{16}-(shell|static|text)$/.test(name)
  || /^aulas-v21-1-(shell|static|text)$/.test(name)
const cacheKey = (url) => new Request(new URL(url, self.location.origin), { credentials: 'omit' })
let writes = Promise.resolve()
let cacheUnavailable = false
function serialized(task) {
  const result = writes.then(task)
  writes = result.catch(() => {})
  return result
}

function isPublicTextApi(url) {
  if (url.href.length > 2048 || [...url.searchParams].length > 6) return false
  if (!/^\/api\/(?:courses|lessons|exercises|vocab|lessons\/\d+|courses\/[a-z0-9-]+\/(?:curriculum|lessons\/\d+(?:\/exercises)?))$/.test(url.pathname)) return false
  return [...url.searchParams].every(([key, value]) =>
    ['course', 'unit', 'lesson', 'activity_type', 'skill', 'objective'].includes(key)
    && /^[a-zA-Z0-9_-]{1,100}$/.test(value))
}

function allowed(response, kind) {
  if (response.status !== 200 || /private|no-store/i.test(response.headers.get('Cache-Control') || '')
    || /\*|cookie|authorization/i.test(response.headers.get('Vary') || '')) return false
  return kind !== 'text' || (response.headers.get('X-Aulas-Offline') === 'public-text-v1'
    && response.headers.get('Content-Type')?.startsWith('application/json'))
}

async function boundedBody(response, limit) {
  const reader = response.body?.getReader()
  if (!reader) return new Uint8Array()
  const chunks = []
  let bytes = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      bytes += value.byteLength
      if (bytes > limit) { void reader.cancel().catch(() => {}); return null }
      chunks.push(value)
    }
    const body = new Uint8Array(bytes)
    let offset = 0
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength }
    return body
  } finally { reader.releaseLock() }
}

async function prune(cache, kind) {
  const limit = LIMITS[kind]
  const entries = []
  for (const key of await cache.keys()) {
    const response = await cache.match(key)
    const at = Number(response?.headers.get('X-Aulas-Cached-At'))
    const bytes = Number(response?.headers.get('X-Aulas-Bytes'))
    if (!at || at > Date.now() || Date.now() - at >= limit.ttl || !Number.isFinite(bytes) || bytes < 0 || bytes > limit.item) {
      await cache.delete(key)
    } else entries.push({ key, at, bytes })
  }
  entries.sort((a, b) => a.at - b.at)
  let size = entries.reduce((sum, entry) => sum + entry.bytes, 0)
  while (entries.length > limit.count || size > limit.bytes) {
    const entry = entries.shift()
    await cache.delete(entry.key)
    size -= entry.bytes
  }
  return { count: entries.length, bytes: size }
}

async function store(kind, request, response) {
  if (!allowed(response, kind)) return false
  const body = await boundedBody(response, LIMITS[kind].item)
  if (!body) return false
  return serialized(async () => {
    const cache = await caches.open(cacheName(kind))
    await cache.put(cacheKey(request.url || request), new Response(body, { headers: {
      'Content-Type': response.headers.get('Content-Type') || 'application/octet-stream',
      'X-Aulas-Cached-At': String(Date.now()), 'X-Aulas-Bytes': String(body.byteLength),
      'X-Aulas-Offline-Source': 'cache',
    } }))
    await prune(cache, kind)
    return true
  })
}

async function cached(kind, request) {
  try {
    return await serialized(async () => {
      const cache = await caches.open(cacheName(kind))
      await prune(cache, kind)
      return cache.match(cacheKey(request.url || request))
    })
  } catch { cacheUnavailable = true; return undefined }
}

// Nenhuma ativação forçada: a versão nova aguarda TODAS as abas antigas fecharem.
self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 30000)
    try {
      const page = await fetch('/', { cache: 'no-store', credentials: 'omit', signal: controller.signal })
      const html = await boundedBody(page.clone(), LIMITS.shell.item)
      if (!html) throw new Error('Shell excede o limite')
      const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', html))]
        .map((byte) => byte.toString(16).padStart(2, '0')).join('')
      if (digest !== HTML_HASH) throw new Error('Shell e worker pertencem a builds diferentes')
      if (!await store('shell', '/', page)) throw new Error('Shell não armazenado')
      for (const url of ['/manifest.webmanifest', '/icon.svg', ...ENTRY]) {
        const response = await fetch(url, { cache: 'no-store', credentials: 'omit', signal: controller.signal })
        if (!await store(url.startsWith('/assets/') ? 'static' : 'shell', url, response)) {
          throw new Error('Instalação incompleta')
        }
      }
    } catch (error) {
      await Promise.all(Object.keys(LIMITS).map((kind) => caches.delete(cacheName(kind))))
      throw error
    } finally { clearTimeout(timeout) }
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const current = Object.keys(LIMITS).map(cacheName)
    for (const name of await caches.keys()) {
      if (ownCache(name) && !current.includes(name)) await caches.delete(name)
    }
    await self.clients.claim()
  })())
})

async function publicText(request) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 6000)
  try {
    // Endpoints editoriais são anônimos: nunca enviar nem persistir credenciais.
    const response = await fetch(request.url, { credentials: 'omit', cache: 'no-store', signal: controller.signal })
    if (allowed(response, 'text')) {
      try { await store('text', request, response.clone()) } catch { cacheUnavailable = true }
      return response
    }
    if (response.status < 500) {
      try {
        await serialized(async () => (await caches.open(cacheName('text'))).delete(cacheKey(request.url)))
      } catch { cacheUnavailable = true }
      return response
    }
    return (await cached('text', request)) || response
  } catch {
    return (await cached('text', request)) || new Response(JSON.stringify({
      detail: 'Texto indisponível offline. Reconecte e abra esta aula para armazená-la.',
    }), { status: 503, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } })
  } finally { clearTimeout(timeout) }
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin
    || request.destination === 'audio' || request.destination === 'video') return
  if (isPublicTextApi(url)) { event.respondWith(publicText(request)); return }
  if (url.pathname.startsWith('/api/')) return
  if (!url.search && ['/manifest.webmanifest', '/icon.svg'].includes(url.pathname)) {
    event.respondWith(cached('shell', request).then((response) => response || fetch(request)))
    return
  }
  if (request.mode === 'navigate') {
    // Uma única cópia do shell, coerente com os assets deste worker, sem URLs pessoais.
    event.respondWith(cached('shell', '/').then((page) => page || fetch(request)))
  } else if (!url.search && ASSETS.includes(url.pathname)) {
    event.respondWith((async () => {
      const existing = await cached('static', request)
      if (existing) return existing
      const response = await fetch(request)
      try { await store('static', request, response.clone()) } catch { cacheUnavailable = true }
      return response
    })())
  }
})

async function status(lessonPath) {
  const text = await serialized(async () => prune(await caches.open(cacheName('text')), 'text'))
  const url = typeof lessonPath === 'string' ? new URL(lessonPath, self.location.origin) : null
  const lesson = url && url.origin === self.location.origin && isPublicTextApi(url)
    ? await cached('text', url.href) : undefined
  return { version: VERSION, ...text, lesson: Boolean(lesson), cacheUnavailable,
    expiresAt: lesson ? Number(lesson.headers.get('X-Aulas-Cached-At')) + LIMITS.text.ttl : null }
}

self.addEventListener('message', (event) => {
  if (!event.source?.url || new URL(event.source.url).origin !== self.location.origin || !event.ports[0]) return
  if (!['PWA_STATUS', 'PWA_CLEAR_TEXT'].includes(event.data?.type)) return
  event.waitUntil((async () => {
    try {
      if (event.data.type === 'PWA_CLEAR_TEXT') {
        await serialized(() => caches.delete(cacheName('text')))
        cacheUnavailable = false
      }
      event.ports[0].postMessage(await status(event.data.lessonPath))
    } catch { event.ports[0].postMessage({ error: true }) }
  })())
})
