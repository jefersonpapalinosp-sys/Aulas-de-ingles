const VERSION = 'aulas-v19-1'
const SHELL_CACHE = `${VERSION}-shell`
const TEXT_CACHE = `${VERSION}-text`
const STATIC_CACHE = `${VERSION}-static`
const OWN_CACHES = [SHELL_CACHE, TEXT_CACHE, STATIC_CACHE]

self.addEventListener('install', (event) => {
  event.waitUntil(
    Promise.all([caches.open(SHELL_CACHE), caches.open(STATIC_CACHE)]).then(
      async ([shell, staticAssets]) => {
        const page = await fetch('/')
        await shell.put('/', page.clone())
        const html = await page.text()
        const assetUrls = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(
          (match) => match[1],
        )
        await Promise.all([
          shell.addAll(['/manifest.webmanifest', '/icon.svg']),
          staticAssets.addAll(assetUrls),
        ])
      },
    ),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('aulas-') && !OWN_CACHES.includes(key))
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

function isPublicTextApi(url) {
  return (
    url.pathname === '/api/lessons' ||
    /^\/api\/lessons\/\d+$/.test(url.pathname) ||
    url.pathname === '/api/exercises' ||
    url.pathname === '/api/vocab'
  )
}

async function networkFirst(request, cacheName, fallback) {
  const cache = await caches.open(cacheName)
  try {
    const response = await fetch(request)
    if (response.ok) await cache.put(request, response.clone())
    return response
  } catch (error) {
    const cached = await cache.match(request)
    if (cached) return cached
    if (fallback) {
      const shell = await caches.open(SHELL_CACHE)
      const page = await shell.match(fallback)
      if (page) return page
    }
    throw error
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(STATIC_CACHE)
  const cached = await cache.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) await cache.put(request, response.clone())
  return response
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  if (request.method !== 'GET' || url.origin !== self.location.origin) return

  // Política fail-closed: dados privados e mídia nunca entram no cache. Mesmo
  // uma mídia com licença compatível permanece online até existir download
  // explícito, cota de armazenamento e exclusão controlada pelo estudante.
  if (request.destination === 'audio' || request.destination === 'video') return

  if (isPublicTextApi(url)) {
    event.respondWith(networkFirst(request, TEXT_CACHE))
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, SHELL_CACHE, '/'))
    return
  }

  if (['script', 'style', 'font', 'image'].includes(request.destination)) {
    event.respondWith(cacheFirst(request))
  }
})
