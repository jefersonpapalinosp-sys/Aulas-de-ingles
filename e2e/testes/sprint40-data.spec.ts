import { randomUUID } from 'node:crypto'
import { expect, test, type Download, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { silentWav } from '../audio-fixture'

async function account(page: Page) {
  const result = await page.request.post('/api/auth/register', { data: {
    email: `s40-${randomUUID()}@example.com`, password: 'synthetic-long-password', display_name: 'Portabilidade E2E',
  } })
  expect(result.status()).toBe(201)
  const data = await result.json()
  const headers = { Authorization: `Bearer ${data.access_token}` }
  const user = await (await page.request.get('/api/auth/me', { headers })).json()
  return { headers, userId: user.id }
}

async function bytes(download: Download): Promise<Buffer> {
  const stream = await download.createReadStream()
  expect(stream).not.toBeNull()
  const chunks: Buffer[] = []
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
  return Buffer.concat(chunks)
}

test('Sprint 40A: exportação por teclado, manifesto e download privado de áudio', async ({ page }) => {
  const { headers } = await account(page)
  const lesson = await (await page.request.get('/api/lessons/31')).json()
  const writing = await page.request.post(`/api/writing/prompts/${lesson.writing_prompts[0].id}/feedback`, {
    headers, data: { text: 'The train is faster than a bus. You should try it.' },
  })
  expect(writing.status()).toBe(200)
  const created = await page.request.post('/api/speaking/attempts', { headers,
    data: { cue_id: lesson.media[0].cues[0].id, duration_ms: 1000, consent: true },
  })
  expect(created.status()).toBe(201)
  const id = (await created.json()).id
  const wav = silentWav()
  expect((await page.request.put(`/api/speaking/attempts/${id}/audio`, {
    headers: { ...headers, 'Content-Type': 'audio/wav' }, data: wav,
  })).status()).toBe(200)
  await page.goto('/meus-dados')
  await expect(page.getByRole('heading', { name: 'Meus dados', exact: true })).toBeVisible()
  expect((await new AxeBuilder({ page }).include('.personal-data-page').analyze()).violations).toEqual([])
  const jsonDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Baixar meus dados em JSON' }).focus()
  await page.keyboard.press('Enter')
  const downloaded = await jsonDownload
  expect(downloaded.suggestedFilename()).toBe('aulas-ingles-dados.json')
  const data = JSON.parse((await bytes(downloaded)).toString())
  expect(data.schema_version).toBe('2.0')
  expect(data.writing).toEqual([])
  expect(data.writing_feedback).toHaveLength(1)
  expect(data.audio_manifest[0].attempt_id).toBe(id)
  expect(data.scope.includes_audio_bytes).toBe(false)
  const audioDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: `Baixar gravação ${id}` }).focus()
  await page.keyboard.press('Space')
  expect(await bytes(await audioDownload)).toEqual(wav)
  const cachedUrls = await page.evaluate(async () => {
    const urls: string[] = []
    for (const name of await caches.keys()) {
      for (const request of await (await caches.open(name)).keys()) urls.push(request.url)
    }
    return urls
  })
  expect(cachedUrls.some((url) => url.includes('/api/me/export') || url.includes('/api/speaking/'))).toBe(false)
  await page.screenshot({ path: test.info().outputPath('meus-dados.png'), fullPage: true })
})

test('Sprint 40A: reflow, inventário isolado e limpeza preservam dados pessoais', async ({ page }) => {
  const { userId } = await account(page)
  await page.goto('/meus-dados')
  await expect(page.getByRole('heading', { name: 'Meus dados', exact: true })).toBeVisible()
  await page.evaluate(async (id) => {
    await navigator.serviceWorker.ready
    localStorage.setItem(`aulas-ingles:writing-draft:v1:${id}:31`, 'Synthetic pending draft')
    localStorage.setItem(`aulas-ingles:writing-draft:v1:${id}:31:revision`, '0')
    localStorage.setItem(`aulas-ingles:writing-draft:v1:${id + 1}:31`, 'Other synthetic account')
  }, userId)
  await page.getByRole('button', { name: 'Atualizar inventário local' }).click()
  await expect(page.locator('.data-inventory div').filter({ hasText: 'Rascunhos de escrita locais' }).locator('dd')).toHaveText('1')
  await page.setViewportSize({ width: 640, height: 360 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('link', { name: 'Voltar ao caderno e ao histórico' }).scrollIntoViewIfNeeded()
  await expect(page.getByRole('link', { name: 'Voltar ao caderno e ao histórico' })).toBeVisible()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Limpar somente textos públicos deste navegador' }).click()
  await expect(page.getByText(/Nenhum dado pessoal ou remoto foi apagado/)).toBeVisible()
  expect(await page.evaluate((id) => localStorage.getItem(`aulas-ingles:writing-draft:v1:${id}:31`), userId)).toBe('Synthetic pending draft')
  expect(await page.evaluate((id) => localStorage.getItem(`aulas-ingles:writing-draft:v1:${id + 1}:31`), userId)).toBe('Other synthetic account')
})
