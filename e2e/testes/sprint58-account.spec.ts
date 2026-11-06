import { expect, test } from '@playwright/test'
import { criarConta, SENHA } from '../journey-helpers'

test('refresh real mantém a conta após recarregar e logout revoga o cookie', async ({ page }) => {
  await criarConta(page, 'Sessão real')
  const refreshed = page.waitForResponse(r => r.url().endsWith('/api/auth/refresh') && r.request().method() === 'POST')
  await page.reload()
  expect((await refreshed).status()).toBe(200)
  await expect(page.getByRole('heading', { name: 'Hoje' })).toBeVisible()
  const menu = page.getByRole('button', { name: /Abrir.*trilha/ })
  if (await menu.isVisible()) await menu.click()
  const loggedOut = page.waitForResponse(r => r.url().endsWith('/api/auth/logout'))
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  expect((await loggedOut).status()).toBe(204)
  expect((await page.request.post('/api/auth/refresh')).status()).toBe(401)
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
})

test('exclusão pela interface remove a conta sintética e impede novo login', async ({ page }) => {
  const email = await criarConta(page, 'Exclusão real')
  await page.goto('/meus-dados')
  await page.getByLabel('Senha atual').fill(SENHA)
  await page.getByLabel('Digite EXCLUIR MINHA CONTA').fill('EXCLUIR MINHA CONTA')
  page.once('dialog', dialog => dialog.accept())
  const deletion = page.waitForResponse(r => r.url().endsWith('/api/me/account') && r.request().method() === 'DELETE')
  await page.getByRole('button', { name: 'Excluir minha conta definitivamente' }).click()
  const response = await deletion
  expect(response.status()).toBe(202)
  expect(await response.json()).toMatchObject({ database_deleted: true, state: 'completed' })
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
  expect((await page.request.post('/api/auth/refresh')).status()).toBe(401)
  expect((await page.request.post('/api/auth/login', { data: { email, password: SENHA } })).status()).toBe(401)
})
