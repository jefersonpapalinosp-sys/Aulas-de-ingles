import { expect, test } from '@playwright/test'

import {
  emailUnico,
  SENHA,
  LEVEL_1_SLUG,
  LEVEL_2_SLUG,
  lessonPath,
  practicePath,
  courseReviewPath,
  studyPath,
  ensureTrailVisible,
  globalLink,
  criarConta,
  iniciarPraticaGuiada,
  avancarAteEnunciado,
} from '../journey-helpers'

test('checkpoint 1–5 do Level 2 usa listening da Aula 3 e restaura o resultado', async ({
  page,
}) => {
  await criarConta(page, 'Checkpoint Level 2 Sprint 25')
  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))

  const checkpointPath = courseReviewPath('1-5', LEVEL_2_SLUG)
  await page.goto(checkpointPath)
  await expect(page).toHaveURL(new RegExp(`${checkpointPath}$`))
  await expect(page.getByRole('heading', { level: 1, name: 'Checkpoint 1–5' })).toBeVisible()
  await expect(page.getByText(/Level 2 · Checkpoint curricular/)).toBeVisible()

  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(
    provenance.getByRole('link', { name: /VOA Learning English — Review of Level 2 Lessons 1–5/ }),
  ).toBeVisible()
  await expect(provenance.getByText('Conteúdo autoral do projeto')).toBeVisible()

  const checkpointAudio = page.locator(
    'audio[aria-label="Conversa da Aula 3 — Level 2"]',
  )
  await expect(checkpointAudio).toBeVisible()
  await expect(checkpointAudio.locator('source')).toHaveAttribute('src', /voa-audio\.voanews\.eu/)
  await expect(page.getByRole('link', { name: 'Rever Level 2 · Aula 3' })).toHaveAttribute(
    'href',
    lessonPath(3, LEVEL_2_SLUG),
  )

  const form = page.locator('.checkpoint-form')
  await expect(form.getByRole('group')).toHaveCount(6)
  for (const answer of [
    'has been worrying',
    'Please throw the old advertisement away.',
    'By the time the meeting began, Mia had left a message.',
    'I see your point, but could you explain what makes it art?',
    'the most convenient',
    'Os dois descrevem eventos anteriores ao encontro, mas atribuem o atraso a causas diferentes.',
  ]) {
    await form.getByRole('radio', { name: answer, exact: true }).check()
  }

  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        '/api/courses/voa-level-2/units/1-5/review/attempts' &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await form.getByRole('button', { name: 'Concluir checkpoint' }).click()
  expect((await saved).status()).toBe(201)

  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.locator('.checkpoint-form')).toHaveCount(0)
})

test('Sprint 26 oferece classificação adjective/adverb com correção no servidor', async ({
  page,
}) => {
  await criarConta(page, 'Classificação Level 2 Sprint 26')
  await page.goto(practicePath(8, LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'The Best Barbecue' })).toBeVisible()

  const session = await iniciarPraticaGuiada(page, 8, LEVEL_2_SLUG)
  const exercise = await avancarAteEnunciado(
    page,
    session,
    /Classifique as palavras da narrativa como adjective ou adverb/,
  )
  await expect(exercise.getByRole('group', { name: 'Classifique cada item' })).toBeVisible()
  await exercise.getByRole('combobox', { name: 'secret' }).selectOption('adjective')
  await exercise.getByRole('combobox', { name: 'seriously' }).selectOption('adverb')
  await exercise.getByRole('combobox', { name: 'loyal' }).selectOption('adjective')
  await exercise.getByRole('combobox', { name: 'strongly' }).selectOption('adverb')
  await exercise.getByRole('button', { name: 'Verificar' }).click()
  await expect(exercise.getByText('Correto')).toBeVisible()
  await expect(exercise.getByText(/complemento autoral/)).toBeVisible()
})

test('checkpoint 6–10 usa listening da Aula 9 e restaura o resultado', async ({ page }) => {
  await criarConta(page, 'Checkpoint Level 2 Sprint 26')
  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))

  const checkpointPath = courseReviewPath('6-10', LEVEL_2_SLUG)
  await page.goto(checkpointPath)
  await expect(page).toHaveURL(new RegExp(`${checkpointPath}$`))
  await expect(page.getByRole('heading', { level: 1, name: 'Checkpoint 6–10' })).toBeVisible()

  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(
    provenance.getByRole('link', { name: /VOA Learning English — Review of Level 2 Lessons 6–10/ }),
  ).toBeVisible()
  await expect(page.locator('audio[aria-label="Conversa da Aula 9 — Level 2"]')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Rever Level 2 · Aula 9' })).toHaveAttribute(
    'href',
    lessonPath(9, LEVEL_2_SLUG),
  )

  const form = page.locator('.checkpoint-form')
  await expect(form.getByRole('group')).toHaveCount(6)
  for (const answer of [
    'in',
    'You should walk across the bridge and stop at the memorial.',
    'The sauce recipe is kept secret by the judges.',
    'must have',
    'I hope to visit Peru next year.',
    'Porque cuidar de um animal é uma grande responsabilidade.',
  ]) {
    await form.getByRole('radio', { name: answer, exact: true }).check()
  }

  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        '/api/courses/voa-level-2/units/6-10/review/attempts' &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await form.getByRole('button', { name: 'Concluir checkpoint' }).click()
  expect((await saved).status()).toBe(201)
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Continuar em Level 2 · Aula 11' })).toHaveAttribute(
    'href',
    lessonPath(11, LEVEL_2_SLUG),
  )
  await page.reload()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.locator('.checkpoint-form')).toHaveCount(0)
})

test('checkpoint 11–15 usa listening da Aula 14, persiste e isola o histórico', async ({
  page,
  request,
}) => {
  await criarConta(page, 'Checkpoint Level 2 Sprint 27')
  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))

  const checkpointPath = courseReviewPath('11-15', LEVEL_2_SLUG)
  await page.goto(checkpointPath)
  await expect(page).toHaveURL(new RegExp(`${checkpointPath}$`))
  await expect(page.getByRole('heading', { level: 1, name: 'Checkpoint 11–15' })).toBeVisible()

  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(
    provenance.getByRole('link', { name: /VOA Learning English — Review of Level 2 Lessons 11–15/ }),
  ).toBeVisible()
  await expect(page.locator('audio[aria-label="Conversa da Aula 14 — Level 2"]')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Rever Level 2 · Aula 14' })).toHaveAttribute(
    'href',
    lessonPath(14, LEVEL_2_SLUG),
  )

  const form = page.locator('.checkpoint-form')
  await expect(form.getByRole('group')).toHaveCount(6)
  for (const answer of [
    'has been snowing',
    'will become',
    'If we protect their habitat, more bees will survive.',
    'So does Anna.',
    'Even though',
    'Sentimentos e experiências que compartilham ou não compartilham.',
  ]) {
    await form.getByRole('radio', { name: answer, exact: true }).check()
  }

  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        '/api/courses/voa-level-2/units/11-15/review/attempts' &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await form.getByRole('button', { name: 'Concluir checkpoint' }).click()
  expect((await saved).status()).toBe(201)
  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  // Desde a Sprint 28 a Aula 16 existe, então o fecho do bloco 11-15 deixa de
  // mandar ao progresso do curso e passa a oferecer a continuação natural.
  await expect(page.getByRole('link', { name: /Continuar em Level 2 · Aula 16/ })).toHaveAttribute(
    'href',
    lessonPath(16, LEVEL_2_SLUG),
  )
  await expect(page.getByRole('link', { name: 'Ver progresso do curso' })).toHaveCount(0)

  await page.reload()
  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.locator('.checkpoint-form')).toHaveCount(0)

  const isolatedEmail = emailUnico()
  const register = await request.post('/api/auth/register', {
    data: {
      email: isolatedEmail,
      password: SENHA,
      display_name: 'Outra conta Sprint 27',
    },
  })
  expect(register.status()).toBe(201)
  const isolatedToken = ((await register.json()) as { access_token: string }).access_token
  const isolated = await request.get('/api/courses/voa-level-2/units/11-15/review', {
    headers: { Authorization: `Bearer ${isolatedToken}` },
  })
  expect(isolated.ok()).toBeTruthy()
  expect(((await isolated.json()) as { latest_attempt: unknown }).latest_attempt).toBeNull()
})

test('Sprint 25 isola a retomada de Hoje entre Level 1 e Level 2', async ({ page }) => {
  await criarConta(page, 'Retomada multi-curso Sprint 25')

  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        '/api/courses/voa-level-2/lessons/1/study-session' &&
      response.request().method() === 'PUT' &&
      response.ok(),
  )
  await page.goto(studyPath(1, 'assistir', LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Budget Cuts' })).toBeVisible()
  await expect(page.getByText(/Level 2 · Aula 1 · estudo guiado/)).toBeVisible()
  await saved

  const today = await globalLink(page, /^Hoje$/)
  await today.click()
  await expect(page).toHaveURL(/\/inicio\?course=voa-level-2$/)
  await expect(page.getByRole('heading', { name: /Continuar a Aula 1/ })).toBeVisible()
  await expect(page.getByText(/Level 2 · Aula 1/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Estudar agora' })).toHaveAttribute(
    'href',
    studyPath(1, 'assistir', LEVEL_2_SLUG),
  )

  const trailDialog = await ensureTrailVisible(page)
  const courseSelect = (trailDialog ?? page).getByRole('combobox', { name: 'Curso' })
  await courseSelect.selectOption(LEVEL_1_SLUG)
  await expect(page).toHaveURL(/\/inicio\?course=voa-level-1$/)
  if (trailDialog) {
    // A troca de curso navega e o drawer remonta. Esperar que ele reassente
    // antes de fechar: sem isso a ação cai durante a transição e o teste fica
    // dependente da ordem de execução. Fechar pelo botão, e não pelo Escape:
    // a tecla vai para o documento e se perde se o drawer remontar no meio,
    // o que fica mais provável à medida que a trilha cresce. O caminho do
    // Escape segue coberto pelo teste dedicado do drawer.
    const reaberto = page.getByRole('dialog', { name: 'Trilha de estudo' })
    await expect(reaberto).toBeVisible()
    await reaberto.getByRole('button', { name: 'Fechar trilha' }).click()
    await expect(reaberto).toHaveCount(0)
  }
  await expect(
    page.getByRole('heading', { name: 'Level 1 · Começar a Aula 1' }),
  ).toBeVisible()
  await expect(page.getByText(/Level 2 · Aula 1/)).toHaveCount(0)
})
