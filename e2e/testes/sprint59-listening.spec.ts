import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { criarConta, SENHA } from '../journey-helpers'

const selection = (page: Page) => page.getByLabel('Meu progresso em Na recepção do hotel')

async function listening(page: Page) {
  await page.goto('/listening')
  await expect(page.getByText('31 de 31 atividades')).toBeVisible()
  await expect(selection(page)).toBeEnabled()
}

test('listening fica a duas ações do menu e abrir a origem não marca conclusão', async ({ page, context }, testInfo) => {
  await criarConta(page, 'Listening acesso')
  const menu = page.getByRole('button', { name: /Abrir.*trilha/ })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('link', { name: 'Listening rápido', exact: true }).click()
  await expect(page).toHaveURL(/\/listening$/)
  await expect(page).toHaveTitle('Listening rápido | Aulas de Inglês')
  await expect(page.locator('#main-content')).toBeFocused()
  await expect(page.getByText('31 de 31 atividades')).toBeVisible()
  await page.getByLabel('Buscar assunto').fill('hotel')
  await expect(page.getByText('1 de 31 atividades')).toBeVisible()
  await expect(selection(page)).toHaveValue('not_started')
  // Só a navegação de teste é substituída; não acessa mídia/conteúdo de terceiros.
  await context.route('https://test-english.com/**', route => route.fulfill({
    contentType: 'text/html', body: '<title>Destino sintético</title><h1>Link externo de ensaio</h1>',
  }))
  const opened = context.waitForEvent('page')
  await page.getByRole('link', { name: /Abrir no Test-English/ }).click()
  const popup = await opened
  await expect(popup).toHaveURL(/test-english\.com\/listening\/a2\/checking-into-a-hotel/)
  await popup.close()
  await expect(selection(page)).toHaveValue('not_started')
  await expect(page.locator('iframe, video, audio')).toHaveCount(0)
  const result = await new AxeBuilder({ page }).include('#main-content').analyze()
  expect(result.violations).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('listening.png') })
})

test('marcação persiste, entra na exportação e a conta pode ser excluída', async ({ page }) => {
  const email = await criarConta(page, 'Listening dados')
  await listening(page)
  await selection(page).selectOption('completed')
  await expect(page.getByText('Marcação confirmada.')).toBeVisible()
  await page.reload()
  await expect(selection(page)).toHaveValue('completed')
  await page.getByLabel('Filtrar por progresso').selectOption('completed')
  await expect(page.getByText('1 de 31 atividades')).toBeVisible()
  const login = await page.request.post('/api/auth/login', { data: { email, password: SENHA } })
  expect(login.status()).toBe(200)
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const exported = await page.request.get('/api/me/export', { headers })
  expect(exported.status()).toBe(200)
  const data = await exported.json()
  expect(data.listening_progress).toMatchObject([{ resource_slug: 'chegada-ao-hotel', state: 'completed', completion_kind: 'self_reported' }])
  expect(data.listening_operations).toHaveLength(1)
  expect(data.lesson_progress).toHaveLength(0)
  expect(data.skill_evidence).toHaveLength(0)
  await page.goto('/meus-dados')
  await page.getByLabel('Senha atual').fill(SENHA)
  await page.getByLabel('Digite EXCLUIR MINHA CONTA').fill('EXCLUIR MINHA CONTA')
  page.once('dialog', dialog => dialog.accept())
  const deleted = page.waitForResponse(r => r.url().endsWith('/api/me/account') && r.request().method() === 'DELETE')
  await page.getByRole('button', { name: 'Excluir minha conta definitivamente' }).click()
  expect((await deleted).status()).toBe(202)
  expect((await page.request.get('/api/me/listening/progress', { headers })).status()).toBe(401)
})

test('duas abas recusam revisão antiga e preservam a marcação mais recente', async ({ page, context }) => {
  await criarConta(page, 'Listening abas')
  await listening(page)
  const other = await context.newPage()
  await listening(other)
  await selection(page).selectOption('completed')
  await expect(page.getByText('Marcação confirmada.')).toBeVisible()
  await selection(other).selectOption('in_progress')
  await expect(other.getByText(/O progresso mudou em outra aba/)).toBeVisible()
  await expect(selection(other)).toHaveValue('completed')
  await other.close()
})

test('offline bloqueia marcação e reconexão permite uma confirmação explícita', async ({ page, context }) => {
  await criarConta(page, 'Listening offline')
  await listening(page)
  await context.setOffline(true)
  try {
    await expect(selection(page)).toBeDisabled()
    await expect(page.getByText(/Conecte-se à internet para abrir/)).toBeVisible()
    await expect(selection(page)).toHaveValue('not_started')
  } finally { await context.setOffline(false) }
  await expect(selection(page)).toBeEnabled()
  await selection(page).selectOption('in_progress')
  await expect(page.getByText('Marcação confirmada.')).toBeVisible()
  await expect(selection(page)).toHaveValue('in_progress')
})
