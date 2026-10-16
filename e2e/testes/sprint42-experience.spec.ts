import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

const password = 'synthetic-sprint42-password'
const practicePath = '/cursos/voa-level-1/aulas/31/exercicios'
const writingPath = '/cursos/voa-level-1/aulas/31/estudar/revisar'

async function createAccount(page: Page): Promise<number> {
  const response = await page.request.post('/api/auth/register', {
    data: {
      email: `s42-${randomUUID()}@example.com`,
      password,
      display_name: 'Sprint 42 probe',
    },
  })
  expect(response.status()).toBe(201)
  const token = (await response.json()).access_token as string
  const profile = await page.request.get('/api/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(profile.status()).toBe(200)
  return (await profile.json()).id as number
}

test('Sprint 42: resposta lenta bloqueia envio duplicado e confirma a tentativa', async ({ page }) => {
  await createAccount(page)
  await page.goto(practicePath)
  await page.getByLabel('Objetivo').selectOption('correct')
  await page.getByRole('button', { name: 'Começar Prática guiada' }).click()

  let attempts = 0
  let release!: () => void
  const gate = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/exercises/*/attempt', async (route) => {
    attempts += 1
    await gate
    await route.continue()
  })

  const question = page.locator('.practice-question')
  await question.getByRole('textbox', { name: 'Resposta do exercício 1' }).fill('faster')
  const verify = question.getByRole('button', { name: 'Verificar' })
  await verify.click()
  await expect(verify).toBeDisabled()
  expect(attempts).toBe(1)
  release()
  await expect(question.getByText('Correto', { exact: true })).toBeVisible()
  expect(attempts).toBe(1)
})

test('Sprint 42: sessão expirada mantém o rascunho local para o próximo login', async ({ page }) => {
  const userId = await createAccount(page)
  await page.goto(writingPath)
  const editor = page.getByRole('textbox', { name: 'Seu texto em inglês' })
  await expect(editor).toBeEnabled()

  await page.route('**/api/writing/prompts/*/draft', async (route) => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({ status: 401, contentType: 'application/json', body: '{}' })
      return
    }
    await route.continue()
  })
  await page.route('**/api/auth/refresh', async (route) => {
    await route.fulfill({ status: 401, contentType: 'application/json', body: '{}' })
  })

  const draft = 'My local draft survives an expired session.'
  await editor.fill(draft)
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()

  const stored = await page.evaluate(
    ({ id, expected }) => Object.entries(localStorage).some(
      ([key, value]) => key.startsWith(`aulas-ingles:writing-draft:v1:${id}:`) && value === expected,
    ),
    { id: userId, expected: draft },
  )
  expect(stored).toBe(true)
})
