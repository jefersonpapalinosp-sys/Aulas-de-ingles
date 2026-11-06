import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { criarConta, SENHA } from '../journey-helpers'

async function open(page: Page, slug = 'hotel-riverside') {
  await page.goto(`/listening/${slug}`)
  await page.getByRole('button', { name: 'Iniciar prática' }).click()
  await expect(page).toHaveURL(/sessao=\d+/)
  await expect(page.locator('audio')).toBeVisible()
  await expect.poll(() => page.locator('audio').evaluate((audio: HTMLAudioElement) => audio.readyState)).toBeGreaterThan(0)
}

test('piloto acessível: áudio real, correção, conclusão e versão preservada após recarga', async ({ page }, info) => {
  test.setTimeout(60_000) // Quatro respostas, recarga, axe e captura no laboratório com CPU limitada.
  await criarConta(page, 'Listening nativo hotel')
  await page.goto('/listening')
  await page.getByRole('link', { name: 'A room at the Riverside Hotel', exact: true }).click()
  await expect(page).toHaveTitle('Prática de listening | Aulas de Inglês')
  await expect(page.locator('audio')).toHaveCount(0)
  await page.getByRole('button', { name: 'Iniciar prática' }).click()
  await expect(page.locator('audio')).toBeVisible()
  await expect.poll(() => page.locator('audio').evaluate((audio: HTMLAudioElement) => audio.duration)).toBeGreaterThan(70)
  expect(await page.locator('audio').evaluate((audio: HTMLAudioElement) => audio.autoplay)).toBe(false)
  await page.getByLabel('Velocidade do áudio').selectOption('0.75')
  expect(await page.locator('audio').evaluate((audio: HTMLAudioElement) => audio.playbackRate)).toBe(0.75)
  const questions = [
    ['1. How many nights is Alex staying?', 'Two'],
    ['2. What time does breakfast start tomorrow?', '7:30'],
    ['3. What can Alex see from the room?', 'The garden'],
    ['4. When must Alex leave the room on Sunday?', 'Before 11:00 a.m.'],
  ]
  for (const [name, option] of questions) {
    const region = page.getByRole('region', { name, exact: true })
    await region.getByLabel(option, { exact: true }).check()
    await region.getByRole('button', { name: 'Confirmar resposta' }).click()
    await expect(region.getByText(/Resposta correta/)).toBeVisible()
  }
  await expect(page.getByText(/Prática concluída/)).toContainText('4 de 4')
  await page.reload()
  await expect(page.getByText(/Prática concluída/)).toContainText('4 de 4')
  await page.getByRole('button', { name: 'Revelar transcrição como apoio' }).click()
  await expect(page.getByRole('heading', { name: 'Transcrição · apoio textual' })).toBeVisible()
  expect((await new AxeBuilder({ page }).include('#main-content').analyze()).violations).toEqual([])
  await page.screenshot({ path: info.outputPath('native-listening.png'), fullPage: true })
})

test('selecione duas, repetição e revelação mantêm a primeira nota', async ({ page }) => {
  await criarConta(page, 'Listening nativo lazer')
  await open(page, 'sabado-com-amigos')
  const region = page.getByRole('region', { name: /1. Which TWO activities/ })
  await region.getByLabel('Ride bikes').check()
  await expect(region.getByRole('button', { name: 'Confirmar resposta' })).toBeDisabled()
  await region.getByLabel('Have lunch at the market').check()
  await region.getByRole('button', { name: 'Confirmar resposta' }).click()
  await expect(region.getByText(/Resposta correta/)).toBeVisible()
  await region.getByLabel('Ride bikes').uncheck()
  await region.getByLabel('Go swimming').check()
  await region.getByRole('button', { name: 'Responder novamente' }).click()
  await expect(region.getByText(/Repetição: a nota inicial foi mantida/)).toBeVisible()
  await expect(page.getByText(/Primeiras respostas/)).toContainText('1 de 3')
  const meeting = page.getByRole('region', { name: /2. Where will they meet/ })
  await meeting.getByRole('button', { name: 'Revelar resposta' }).click()
  await expect(meeting.getByText(/Resposta revelada/)).toBeVisible()
  await expect(page.getByText(/Primeiras respostas/)).toContainText('1 de 3')
})

test('mapa com alternativa textual e respostas exportadas sem gabarito não revelado', async ({ page }) => {
  const email = await criarConta(page, 'Listening nativo mapa')
  await open(page, 'caminho-ao-museu')
  await expect(page.getByRole('table')).toBeVisible()
  await expect(page.locator('figcaption')).toContainText('North is at the top')
  expect((await new AxeBuilder({ page }).include('#main-content').analyze()).violations).toEqual([])
  const region = page.getByRole('region', { name: /2. Which letter/ })
  await region.getByLabel('B', { exact: true }).check()
  await region.getByRole('button', { name: 'Confirmar resposta' }).click()
  await expect(region.getByText(/Resposta correta/)).toBeVisible()
  const login = await page.request.post('/api/auth/login', { data: { email, password: SENHA } })
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const exported = await page.request.get('/api/me/export', { headers })
  expect(exported.status()).toBe(200)
  const data = await exported.json()
  expect(data.native_listening_sessions).toHaveLength(1)
  expect(data.native_listening_responses[0].payload).toMatchObject({ question_id: 'museum', selected_ids: ['b'] })
  expect(data.lesson_progress).toHaveLength(0)
  expect(data.skill_evidence).toHaveLength(0)
})

test('offline bloqueia revelação e a mídia continua fora do cache persistente', async ({ page, context }) => {
  await criarConta(page, 'Listening nativo offline')
  await open(page)
  await context.setOffline(true)
  try {
    await expect(page.getByText(/Sem confirmação online/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Revelar resposta' }).first()).toBeDisabled()
    const cached = await page.evaluate(async () => {
      const paths: string[] = []
      for (const name of await caches.keys()) {
        for (const request of await (await caches.open(name)).keys()) paths.push(new URL(request.url).pathname)
      }
      return paths.filter(path => path.includes('/api/listening/'))
    })
    expect(cached).toEqual([])
  } finally { await context.setOffline(false) }
  await expect(page.getByRole('button', { name: 'Revelar resposta' }).first()).toBeEnabled()
})
