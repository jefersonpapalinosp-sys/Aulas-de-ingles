import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'senha-bem-grande'

async function register(page: Page): Promise<void> {
  const email = `sprint41-${Date.now()}-${Math.random()}@example.invalid`
  await page.goto('/')
  await page.getByRole('button', { name: 'Ainda não tenho conta' }).click()
  await page.getByLabel('Nome').fill('Teste Sprint 41')
  await page.getByLabel('E-mail').fill(email)
  await page.getByLabel('Senha').fill(PASSWORD)
  await page.getByRole('button', { name: 'Criar conta' }).click()
  await expect(page).toHaveURL(/\/inicio$/)
  await expect(page.getByRole('heading', { name: 'Hoje' })).toBeVisible()
}

test('rota anuncia contexto, move foco e o drawer nativo mantém modalidade', async ({ page }) => {
  await register(page)

  await expect(page).toHaveTitle('Hoje | Aulas de Inglês')
  await expect(page.locator('.sr-only[role="status"]')).toHaveText('Hoje carregada.')

  const opener = page.getByRole('button', { name: /Abrir trilha de aulas/ })
  let courses = page.getByRole('navigation', { name: 'Atalhos', exact: true })
    .getByRole('link', { name: 'Cursos' })
  if (await opener.isVisible()) {
    await opener.click()
    const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
    await expect(dialog).toBeVisible()
    expect(await dialog.evaluate((element) =>
      element instanceof HTMLDialogElement && element.open && element.matches(':modal'),
    )).toBe(true)

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(opener).toBeFocused()

    await opener.click()
    courses = page.getByRole('dialog', { name: 'Trilha de estudo' })
      .getByRole('link', { name: 'Cursos' })
  }

  await courses.click()
  await expect(page).toHaveURL(/\/cursos$/)
  await expect(page).toHaveTitle('Cursos | Aulas de Inglês')
  await expect(page.locator('.sr-only[role="status"]')).toHaveText('Cursos carregada.')
  await expect(page.locator('#main-content')).toBeFocused()
})

test('registra baseline das quatro rotas críticas sem percentual inventado', async ({
  browserName,
  page,
}, testInfo) => {
  test.skip(browserName !== 'chromium', 'Métrica comparável registrada no motor de referência.')
  await register(page)

  const routes = [
    ['/inicio', 'Hoje | Aulas de Inglês'],
    ['/cursos/voa-level-1/aulas/31', 'Aula 31 | Aulas de Inglês'],
    ['/cursos/voa-level-1/aulas/31/estudar/assistir', 'Estudo da Aula 31 | Aulas de Inglês'],
    ['/caderno', 'Caderno | Aulas de Inglês'],
  ] as const
  const measurements: Record<string, { navigation_ms: number; dom_content_loaded_ms: number }> = {}

  for (const [path, title] of routes) {
    await page.goto(path)
    await expect(page).toHaveTitle(title)
    await expect(page.locator('#main-content')).toBeFocused()
    const timing = await page.evaluate(() => {
      const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
      return {
        navigation_ms: Number(navigation.duration.toFixed(2)),
        dom_content_loaded_ms: Number(navigation.domContentLoadedEventEnd.toFixed(2)),
      }
    })
    measurements[path] = timing
    expect(timing.navigation_ms).toBeLessThan(5_000)
  }

  await testInfo.attach('sprint41-route-baseline.json', {
    body: Buffer.from(JSON.stringify({
      environment: 'stack E2E descartável; Chromium desktop; cache normal',
      goal: 'navigation_ms < 5000 em CI; baseline não é promessa de produção',
      measurements,
    }, null, 2)),
    contentType: 'application/json',
  })
})
