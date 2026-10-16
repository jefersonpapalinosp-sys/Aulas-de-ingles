import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

const lessonPath = '/cursos/voa-level-1/aulas/31'
async function prepare(page: Page) {
  const account = await page.request.post('/api/auth/register', { data: {
    email: `s39e-${randomUUID()}@example.com`, password: 'synthetic-pwa-password', display_name: 'PWA probe',
  } })
  expect(account.status()).toBe(201)
  await page.goto(lessonPath)
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
    if (!navigator.serviceWorker.controller) await new Promise<void>((resolve) =>
      navigator.serviceWorker.addEventListener('controllerchange', () => resolve(), { once: true }))
  })
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
  await page.getByText('Offline e atualizações', { exact: true }).click()
  await expect(page.getByText(/Texto desta aula armazenado até/)).toBeVisible()
}

test('Sprint 39E: texto visitado e jornada abrem offline; aula ausente informa erro', async ({ page, context }) => {
  await prepare(page)
  await page.screenshot({ path: test.info().outputPath('offline-panel.png') })
  await context.setOffline(true)
  await page.goto(`${lessonPath}/estudar/preparar`)
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
  await page.getByText('Offline e atualizações', { exact: true }).click()
  await expect(page.getByText(/Texto desta aula armazenado até/)).toBeVisible()
  await expect(page.getByText(/Áudio e vídeo continuam online/)).toBeVisible()
  await page.goto('/cursos/voa-level-1/aulas/32')
  await expect(page.getByRole('button', { name: 'Tentar de novo' })).toBeVisible()
  await page.getByText('Offline e atualizações', { exact: true }).click()
  await expect(page.getByText(/Texto desta aula não armazenado/)).toBeVisible()
  await context.setOffline(false)
})

test('Sprint 39E: limpeza explícita preserva rascunho e cache não contém credenciais', async ({ page }) => {
  await prepare(page)
  const entries = await page.evaluate(async () => {
    localStorage.setItem('pwa-synthetic-draft', 'do not delete')
    const names = (await caches.keys()).filter((name) => name.endsWith('-text'))
    return Promise.all(names.map(async (name) => (await (await caches.open(name)).keys())
      .map((key) => ({ url: key.url, auth: key.headers.get('Authorization'), cookie: key.headers.get('Cookie') }))))
  })
  expect(entries.flat().length).toBeGreaterThan(0)
  for (const entry of entries.flat()) {
    expect(entry.auth).toBeNull(); expect(entry.cookie).toBeNull()
    expect(entry.url).not.toContain('/api/me')
    expect(entry.url).not.toContain('/speaking')
  }
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Limpar somente textos públicos' }).click()
  await expect(page.getByText(/Texto desta aula armazenado até/)).toBeVisible()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Limpar somente textos públicos' }).click()
  await expect(page.getByText(/Textos removidos/)).toBeVisible()
  await expect(page.getByText(/Texto desta aula não armazenado/)).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('pwa-synthetic-draft'))).toBe('do not delete')
  expect(await page.evaluate(() => caches.keys())).toEqual(expect.arrayContaining([
    expect.stringMatching(/^aulas-pwa-[a-f0-9]{16}-shell$/),
    expect.stringMatching(/^aulas-pwa-[a-f0-9]{16}-static$/),
  ]))
})
