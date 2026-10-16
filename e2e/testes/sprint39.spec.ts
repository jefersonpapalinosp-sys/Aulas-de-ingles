import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const path = '/cursos/voa-level-1/aulas/31/estudar/assistir'
async function account(page: Page) {
  const response = await page.request.post('/api/auth/register', {
    data: { email: `s39-${randomUUID()}@example.com`, password: 'synthetic-long-password', display_name: 'Sprint 39 test' },
  })
  expect(response.status()).toBe(201)
  return { Authorization: `Bearer ${(await response.json()).access_token}` }
}

// Exercita os eventos do player e a API real sem depender do MP3 externo ou de som.
async function position(page: Page, seconds: number, end = false) {
  await page.locator('.audio-player audio').evaluate((element, args) => {
    Object.defineProperty(element, 'duration', { configurable: true, value: 209 })
    Object.defineProperty(element, 'currentTime', { configurable: true, writable: true, value: args.seconds })
    element.dispatchEvent(new Event('loadedmetadata'))
    element.dispatchEvent(new Event(args.end ? 'ended' : 'timeupdate'))
    if (args.end) { element.dispatchEvent(new Event('pause')); element.dispatchEvent(new Event('timeupdate')) }
  }, { seconds, end })
}

test('Sprint 39A: áudio offline e conclusão não ressuscitam posição atrasada', async ({ page }) => {
  const headers = await account(page)
  const lesson = await (await page.request.get('/api/lessons/31')).json()
  const url = `/api/media/${lesson.media[0].id}/position`
  await page.goto(path)
  await expect(page.getByText('Posição sincronizada com sua conta.')).toBeVisible()
  await page.context().setOffline(true)
  await position(page, 42)
  await position(page, 209, true)
  await expect(page.locator('.media-sync')).toContainText('pendente')
  await page.context().setOffline(false)
  await expect(page.getByText('Posição sincronizada com sua conta.')).toBeVisible()
  const remote = await (await page.request.get(url, { headers })).json()
  expect(remote).toMatchObject({ position_seconds: 0, completed: true, revision: 2 })
  const stale = await page.request.put(url, { headers, data: {
    position_seconds: 42, expected_revision: 0, completed: false,
    changed_at: new Date().toISOString(), operation_key: randomUUID(),
  } })
  expect(stale.status()).toBe(409)
  await page.reload()
  await expect(page.locator('.audio-time')).toContainText('0:00')
})

test('Sprint 39A: conflito de áudio mantém posição local até escolha por teclado', async ({ page }) => {
  const headers = await account(page)
  const lesson = await (await page.request.get('/api/lessons/31')).json()
  const url = `/api/media/${lesson.media[0].id}/position`
  await page.goto(path)
  await expect(page.getByText('Posição sincronizada com sua conta.')).toBeVisible()
  await page.request.put(url, { headers, data: {
    position_seconds: 20, expected_revision: 0, completed: false,
    changed_at: new Date().toISOString(), operation_key: randomUUID(),
  } })
  await position(page, 42)
  const conflict = page.getByRole('region', { name: 'Conflito de posição' })
  await expect(conflict).toContainText('0:42')
  await expect(conflict).toContainText('0:20')
  expect((await new AxeBuilder({ page }).include('[aria-label="Conflito de posição"]').analyze()).violations).toEqual([])
  const keep = page.getByRole('button', { name: 'Manter posição deste dispositivo' })
  await keep.focus(); await page.keyboard.press('Enter')
  await expect(conflict).toHaveCount(0)
  await expect(page.getByText('Posição sincronizada com sua conta.')).toBeVisible()
  expect(await (await page.request.get(url, { headers })).json()).toMatchObject({ position_seconds: 42, revision: 2 })
})

test('Sprint 39A: interação registra tempo; sinal de aba oculta interrompe eventos', async ({ page }) => {
  test.setTimeout(60000)
  const headers = await account(page)
  await page.goto(path)
  const status = page.getByRole('complementary', { name: 'Tempo ativo de estudo' })
  await expect(status).toContainText('Medição iniciada')
  await page.bringToFront()
  await page.getByRole('button', { name: 'Mostrar transcrição' }).click()
  const firstEvent = await page.waitForResponse((response) => response.url().endsWith('/api/me/activity/events') && response.ok(), { timeout: 22000 })
  expect((await firstEvent.json()).credited_ms).toBeGreaterThan(0)
  // Headless mantém páginas em foco. Injeta somente o sinal DOM de visibilidade;
  // não representa homologação de foco do sistema operacional ou dispositivo real.
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await page.waitForTimeout(1000) // Aguarda o flush do intervalo parcial.
  const before = await (await page.request.get('/api/me/export', { headers })).json()
  await page.waitForTimeout(17000) // Janela maior que um heartbeat real, sem fabricar tempo.
  const after = await (await page.request.get('/api/me/export', { headers })).json()
  expect(after.activity_events.length).toBe(before.activity_events.length)
})
