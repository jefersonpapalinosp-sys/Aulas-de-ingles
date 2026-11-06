import { expect, test, type Page } from '@playwright/test'

async function controlled(page: Page) {
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
    if (!navigator.serviceWorker.controller) await new Promise<void>((resolve) =>
      navigator.serviceWorker.addEventListener('controllerchange', () => resolve(), { once: true }))
  })
}

test.beforeEach(async ({ request }) => {
  expect((await request.post('/__test__/release', { headers: { 'X-Test-Release': 'aaaaaaaaaaaaaaaa' } })).ok()).toBe(true)
})

test('confirmação ativa a nova release com duas abas e só a solicitante recarrega', async ({ page, context, request }) => {
  await page.goto('/')
  await controlled(page)
  await page.locator('#draft').fill('Texto não enviado')
  await page.evaluate(async () => {
    localStorage.setItem('synthetic-draft', 'draft preserved')
    await new Promise<void>((resolve, reject) => {
      const open = indexedDB.open('synthetic-queue', 1)
      open.onupgradeneeded = () => open.result.createObjectStore('pending')
      open.onerror = () => reject(open.error)
      open.onsuccess = () => {
        const tx = open.result.transaction('pending', 'readwrite')
        tx.objectStore('pending').put('answer preserved', 'one')
        tx.oncomplete = () => { open.result.close(); resolve() }
      }
    })
    await fetch('/api/lessons/31')
  })
  const second = await context.newPage()
  await second.goto('/')
  await controlled(second)
  let firstNavigations = 0
  let secondNavigations = 0
  page.on('framenavigated', (frame) => { if (frame === page.mainFrame()) firstNavigations++ })
  second.on('framenavigated', (frame) => { if (frame === second.mainFrame()) secondNavigations++ })
  expect(await (await request.get('/sw.js')).text()).not.toContain("type === 'SKIP_WAITING'")
  await request.post('/__test__/release', { headers: { 'X-Test-Release': 'bbbbbbbbbbbbbbbb' } })
  expect(await page.evaluate(() => caches.keys())).toContain('aulas-pwa-aaaaaaaaaaaaaaaa-text')
  await expect(page.locator('#draft')).toHaveValue('Texto não enviado')

  const activation = await page.evaluate(async () => {
    const previous = navigator.serviceWorker.controller
    let reloadCalled = false
    let targetActivated = false
    const { updateAppAndReload } = await import('/app-update.js?e2e')
    await updateAppAndReload({ reload: () => {
      reloadCalled = true
      const current = navigator.serviceWorker.controller
      targetActivated = Boolean(current && current !== previous && current.state === 'activated')
    } })
    return { reloadCalled, targetActivated }
  })
  expect(activation).toEqual({ reloadCalled: true, targetActivated: true })

  await expect.poll(() => page.evaluate(() => caches.keys())).not.toContain('aulas-pwa-aaaaaaaaaaaaaaaa-text')
  await expect(page.locator('#release')).toHaveText('aaaaaaaaaaaaaaaa')
  await expect(second.locator('#release')).toHaveText('aaaaaaaaaaaaaaaa')
  expect(firstNavigations).toBe(0)
  expect(secondNavigations).toBe(0)

  await page.reload()
  await expect(page.locator('#release')).toHaveText('bbbbbbbbbbbbbbbb')
  expect(firstNavigations).toBe(1)
  expect(secondNavigations).toBe(0)
  expect(await page.evaluate(() => localStorage.getItem('synthetic-draft'))).toBe('draft preserved')
  expect(await page.evaluate(() => new Promise((resolve) => {
    const open = indexedDB.open('synthetic-queue', 1)
    open.onsuccess = () => {
      const read = open.result.transaction('pending').objectStore('pending').get('one')
      read.onsuccess = () => { open.result.close(); resolve(read.result) }
    }
  }))).toBe('answer preserved')
})

test('instalação com shell divergente falha sem perder versão anterior offline', async ({ page, context, request }) => {
  await page.goto('/')
  await controlled(page)
  await page.evaluate(() => fetch('/api/lessons/31'))
  await request.post('/__test__/release', { headers: { 'X-Test-Release': 'cccccccccccccccc', 'X-Test-Broken': '1' } })
  await page.evaluate(async () => {
    const registration = (await navigator.serviceWorker.getRegistration())!
    const finished = new Promise<void>((resolve) => registration.addEventListener('updatefound', () => {
      const worker = registration.installing!
      worker.addEventListener('statechange', () => { if (worker.state === 'redundant') resolve() })
    }, { once: true }))
    await registration.update()
    await finished
  })
  expect(await page.evaluate(() => caches.keys())).toContain('aulas-pwa-aaaaaaaaaaaaaaaa-shell')
  expect(await page.evaluate(() => caches.keys())).not.toContain('aulas-pwa-cccccccccccccccc-shell')
  await context.setOffline(true)
  await page.reload()
  await expect(page.locator('#release')).toHaveText('aaaaaaaaaaaaaaaa')
  expect(await page.evaluate(async () => (await fetch('/api/lessons/31')).json())).toEqual({ title: 'Synthetic lesson' })
  await context.setOffline(false)
})
