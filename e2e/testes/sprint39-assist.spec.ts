import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

// Interface com respostas simuladas; concorrência/consumo real são testados no PostgreSQL.
// Não habilita assistência nem envia texto a provedor no ambiente E2E.
test('Sprint 39F: cota explícita e retry de escrita preservam chave e texto', async ({ page }) => {
  const account = await page.request.post('/api/auth/register', {
    data: { email: `quota-${randomUUID()}@example.com`, password: 'synthetic-long-password', display_name: 'Quota test' },
  })
  expect(account.status()).toBe(201)
  await page.route('**/api/assist/status', (route) => route.fulfill({ json: {
    transcription_enabled: false, writing_enabled: true, evaluation_only: true,
    daily_quota: 5, used_today: 3, remaining_today: 2, reserved_today: 1, consumed_today: 2,
    quota_timezone: 'UTC', quota_resets_at: '2026-10-15T00:00:00Z',
    retention_days: 30, cost_microusd_today: 200, cost_incomplete: true,
  } }))
  const keys: string[] = []
  await page.route('**/api/writing/prompts/*/feedback', async (route) => {
    keys.push(route.request().postDataJSON().operation_key)
    if (keys.length === 1) await route.abort('failed')
    else await route.fulfill({ status: 409, json: { detail: 'Análise já iniciada.' } })
  })
  await page.goto('/cursos/voa-level-1/aulas/31/estudar/revisar')
  const workspace = page.locator('.writing-workspace')
  const text = workspace.getByRole('textbox', { name: 'Seu texto em inglês' })
  await text.fill('The train is faster than the bus. Keep this draft.')
  await expect(workspace.getByText('Rascunho salvo.')).toBeVisible()
  await expect(workspace).toContainText('1 reservadas; 2 utilizadas')
  await expect(workspace).toContainText('meia-noite UTC')
  await expect(workspace).toContainText('parcial: há chamadas sem custo confirmado')
  await workspace.getByRole('checkbox').check()
  const analyze = workspace.getByRole('button', { name: 'Analisar texto' })
  await analyze.focus()
  await page.keyboard.press('Enter')
  await expect(workspace).toContainText('Análise indisponível')
  await analyze.focus()
  await page.keyboard.press('Enter')
  await expect(workspace).toContainText('Análise já iniciada')
  await expect(text).toHaveValue('The train is faster than the bus. Keep this draft.')
  expect(keys).toHaveLength(2)
  expect(keys[0]).toMatch(/^[a-f0-9-]{36}$/)
  expect(keys[1]).toBe(keys[0])
})
