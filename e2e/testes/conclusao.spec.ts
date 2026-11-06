import { expect, test } from '@playwright/test'

import AxeBuilder from '@axe-core/playwright'

import {
  LEVEL_2_SLUG,
  coursePath,
  courseCompletionPath,
  expectNoHorizontalScroll,
  criarConta,
} from '../journey-helpers'

test('conclusão separa progresso, evidência, certificado e Level 2 opcional', async ({ page }) => {
  await criarConta(page, 'Página de conclusão Sprint 24 E2E')
  await page.goto(courseCompletionPath())

  await expect(
    page.getByRole('heading', { level: 1, name: /Conclusão de Let's Learn English — Level 1/ }),
  ).toBeVisible()
  const overview = page.getByRole('region', { name: 'Seu percurso no conteúdo publicado' })
  const metricValue = (label: string) =>
    overview
      .locator('dt')
      .filter({ hasText: new RegExp(`^${label}$`) })
      .locator('..')
      .locator('dd')
      .first()
  await expect(metricValue('Conteúdo publicado')).toHaveText('52')
  await expect(metricValue('Aulas vistas')).toHaveText('0 / 52')
  await expect(metricValue('Aulas concluídas')).toHaveText('0 / 52')
  await expect(page.getByRole('progressbar', { name: 'Aulas concluídas no recorte publicado' }))
    .toHaveAttribute('aria-valuenow', '0')

    for (const unit of [
    'Aulas 1–5',
    'Aulas 6–10',
    'Aulas 11–15',
    'Aulas 16–20',
    'Aulas 21–25',
    'Aulas 26–30',
    'Aulas 31–40',
    'Aulas 40–44',
    'Aulas 45–49',
    'Aulas 50–52',
  ]) {
    await expect(page.getByRole('link', { name: new RegExp(unit) })).toBeVisible()
  }
  await expect(
    page.getByRole('heading', { name: 'Certificado do recorte: ainda não elegível' }),
  ).toBeVisible()
  await expect(page.getByText(/Regra deste recorte: 52 aulas e 10 checkpoints/)).toBeVisible()
  await expect(page.locator('[download], iframe')).toHaveCount(0)

  await expect(page.getByText('Recomendado e opcional.')).toBeVisible()
  await expect(page.getByText(/Level 2 · Intermediário · Disponível/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Conhecer Level 2' })).toHaveAttribute(
    'href',
    coursePath(LEVEL_2_SLUG),
  )

  const diagnostic = page
    .getByRole('heading', { name: "Preparação para Let's Learn English — Level 2" })
    .locator('..')
  await expect(diagnostic.getByText(/não é prova, não gera nota/)).toBeVisible()
  const guidance = diagnostic.getByRole('button', { name: 'Ver orientação' })
  await expect(guidance).toBeDisabled()
  for (const option of await diagnostic.getByLabel('Em parte').all()) await option.check()
  await expect(guidance).toBeEnabled()
  await guidance.click()
  await expect(
    diagnostic.getByRole('heading', { name: 'Explore Level 2 mantendo revisões' }),
  ).toBeFocused()

  const accessibility = await new AxeBuilder({ page })
    .include('.course-completion-page')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(
    accessibility.violations.filter(
      ({ impact }) => impact === 'serious' || impact === 'critical',
    ),
  ).toEqual([])
  await expectNoHorizontalScroll(page)
})
