import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'

const writingPath = '/cursos/voa-level-1/aulas/31/estudar/revisar'

async function account(page: Page) {
  const response = await page.request.post('/api/auth/register', {
    data: { email: 's38-' + randomUUID() + '@example.com', password: 'synthetic-long-password', display_name: 'Sprint 38 test' },
  })
  expect(response.status()).toBe(201)
  return { Authorization: 'Bearer ' + (await response.json()).access_token }
}

test('Sprint 38: dois dispositivos preservam rascunhos e resolvem conflito explicitamente', async ({ page, browser, baseURL }) => {
  await account(page)
  await page.goto(writingPath)
  const editor = page.getByRole('textbox', { name: 'Seu texto em inglês' })
  await expect(editor).toBeEnabled()
  const second = await browser.newContext({ baseURL, storageState: await page.context().storageState() })
  try {
    const other = await second.newPage()
    await other.goto(writingPath)
    const otherEditor = other.getByRole('textbox', { name: 'Seu texto em inglês' })
    await expect(otherEditor).toBeEnabled()
    await editor.fill('My first device uses the train.')
    await expect(page.getByText('Rascunho salvo.')).toBeVisible()
    await otherEditor.fill('My second device uses the bus.')
    await expect(other.getByRole('heading', { name: 'Há duas versões do rascunho' })).toBeVisible()
    await expect(otherEditor).toHaveValue('My second device uses the bus.')
    await expect(other.getByRole('textbox', { name: 'Texto salvo na conta' })).toHaveValue('My first device uses the train.')
    await other.getByRole('button', { name: 'Preparar cópia dos dois' }).click()
    await expect(other.getByRole('textbox', { name: 'Selecione e copie os dois textos' })).toHaveValue(/first device[\s\S]*second device|second device[\s\S]*first device/)
    expect((await new AxeBuilder({ page: other }).include('.writing-conflict').analyze()).violations).toEqual([])
    await other.getByRole('button', { name: 'Manter meu texto' }).click()
    await expect(other.getByText('Rascunho salvo.')).toBeVisible()
    await page.reload()
    await expect(editor).toHaveValue('My second device uses the bus.')
  } finally {
    await second.close()
  }
})

test('Sprint 38: análise atrasada não avalia o texto editado', async ({ page }) => {
  await account(page)
  await page.goto(writingPath)
  const editor = page.getByRole('textbox', { name: 'Seu texto em inglês' })
  await expect(editor).toBeEnabled()
  await editor.fill('The train is faster than the bus. You should take the train.')
  let release!: () => void
  let reached!: () => void
  const ready = new Promise<void>((resolve) => { reached = resolve })
  const gate = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/writing/prompts/*/feedback', async (route) => {
    const result = await route.fetch()
    reached()
    await gate
    await route.fulfill({ response: result })
  })
  await page.getByRole('button', { name: 'Analisar texto' }).click()
  await ready
  await editor.fill('Another text, still being written.')
  release()
  await expect(page.getByRole('button', { name: 'Analisar texto' })).toBeEnabled()
  await expect(page.locator('.writing-feedback')).toHaveCount(0)
  await expect(editor).toHaveValue('Another text, still being written.')
})

test('Sprint 38: resposta perdida repete a chave sem duplicar SM-2', async ({ page }) => {
  const headers = await account(page)
  expect((await page.request.put('/api/lessons/31/studied', { headers })).status()).toBe(204)
  await page.goto('/revisar?course=voa-level-1')
  await page.getByRole('button', { name: 'Mostrar resposta' }).click()
  const requests: unknown[] = []
  let firstResult: Record<string, unknown>
  let secondResult: Record<string, unknown>
  await page.route('**/api/review/*/grade', async (route) => {
    requests.push(route.request().postDataJSON())
    const result = await route.fetch()
    if (requests.length === 1) {
      firstResult = await result.json()
      await route.abort('failed')
    } else {
      secondResult = await result.json()
      await route.fulfill({ response: result })
    }
  })
  await page.getByRole('button', { name: /Bom/ }).click()
  await expect(page.getByText('Resultado não confirmado. Sua resposta foi preservada.')).toBeVisible()
  await page.getByRole('button', { name: 'Reenviar a mesma avaliação' }).click()
  await expect(page.getByText(/volta amanhã/)).toBeVisible()
  expect(requests).toHaveLength(2)
  expect(requests[1]).toEqual(requests[0])
  expect(secondResult!).toEqual(firstResult!)
  expect(secondResult!.repetitions).toBe(1)
})

test('Sprint 38: conclusões concorrentes e última revisão atualizam Hoje', async ({ page }) => {
  const headers = await account(page)
  const results = await Promise.all([
    page.request.put('/api/lessons/31/study-session', { headers, data: { current_step: 'assistir', completed_steps: ['preparar'], expected_revision: 0 } }),
    page.request.put('/api/lessons/31/study-session', { headers, data: { current_step: 'praticar', completed_steps: ['estudar'], expected_revision: 0 } }),
  ])
  expect(results.map((response) => response.status())).toEqual([200, 200])
  const lesson = await (await page.request.get('/api/lessons/31')).json()
  expect((await page.request.post('/api/review/items/' + lesson.vocab[0].id, { headers })).status()).toBe(200)
  // Aquece o cache de Hoje e usa somente navegação SPA a partir daqui.
  await page.goto('/inicio?course=voa-level-1')
  await expect(page.locator('.today-recommendation')).toContainText('Revisar')
  await page.getByRole('link', { name: 'Estudar agora' }).click()
  await expect(page).toHaveURL(/\/revisar/)
  let todayReads = 0
  page.on('request', (request) => { if (request.url().includes('/api/me/today')) todayReads += 1 })
  await page.getByRole('button', { name: 'Mostrar resposta' }).click()
  await page.getByRole('button', { name: /Bom/ }).click()
  await expect(page.getByRole('heading', { name: 'Nada para revisar agora' })).toBeVisible()
  await page.getByRole('link', { name: '← Hoje e mapa' }).click()
  await expect(page.getByRole('heading', { name: 'Hoje' })).toBeVisible()
  await expect.poll(() => todayReads).toBeGreaterThan(0)
  await expect(page.locator('.today-recommendation')).not.toContainText('Revisar')
  const session = await (await page.request.get('/api/lessons/31/study-session', { headers })).json()
  expect(session.completed_steps).toEqual(['preparar', 'estudar'])
  const summary = await (await page.request.get('/api/review/summary', { headers })).json()
  expect(summary.due_now).toBe(0)
})
