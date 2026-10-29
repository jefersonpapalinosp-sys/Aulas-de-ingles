import { randomUUID } from 'node:crypto'
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('validação nativa associa erros e ajuda no cadastro e no plano semanal', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  const email = page.getByLabel('E-mail', { exact: true })
  const password = page.getByLabel('Senha', { exact: true })
  await expect(email).toHaveAttribute('aria-invalid', 'true')
  await expect(password).toHaveAttribute('aria-invalid', 'true')
  await email.fill(`sprint49-${randomUUID()}@example.com`)
  await expect(email).toHaveAttribute('aria-invalid', 'false')
  await expect(password).toHaveAttribute('aria-invalid', 'true')

  await page.getByRole('button', { name: 'Ainda não tenho conta' }).click()
  await expect(password).toHaveAccessibleDescription('No mínimo 8 caracteres.')
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByLabel('Nome', { exact: true }).fill('Teste de formulários')
  await password.fill('senha-bem-grande')
  expect((await new AxeBuilder({ page }).include('.login-caixa').analyze()).violations).toEqual([])
  await page.getByRole('button', { name: 'Criar conta', exact: true }).click()
  await expect(page).toHaveURL(/\/inicio$/)

  const minutes = page.getByLabel('Minutos por semana', { exact: true })
  await minutes.fill('29')
  await page.getByRole('button', { name: 'Salvar plano', exact: true }).click()
  await expect(minutes).toHaveAttribute('aria-invalid', 'true')
  const errorId = (await minutes.getAttribute('aria-describedby'))!.split(' ').at(-1)!
  expect(await page.evaluate((id) => document.getElementById(id)?.getAttribute('role'), errorId)).toBe('alert')
  expect((await new AxeBuilder({ page }).include('.today-plan').analyze()).violations).toEqual([])
  await minutes.fill('45')
  await expect(minutes).toHaveAttribute('aria-invalid', 'false')
  await page.getByRole('button', { name: 'Salvar plano', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Plano salvo.' })).toBeVisible()
})
