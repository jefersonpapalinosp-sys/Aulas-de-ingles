import { expect, test } from '@playwright/test'

import {
  emailUnico,
  SENHA,
  escapeRegex,
  LEVEL_1_SLUG,
  LEVEL_2_SLUG,
  coursePath,
  courseCompletionPath,
  lessonPath,
  courseReviewPath,
  unitPath,
  assessmentPath,
  criarConta,
} from '../journey-helpers'

test('Sprint 36 publica as Aulas 26–30 e fecha o bloco com referências adjacentes', async ({
  page,
  request,
}) => {
  const curriculumResponse = await request.get(`/api/courses/${LEVEL_1_SLUG}/curriculum`)
  expect(curriculumResponse.ok()).toBeTruthy()
  const curriculum = (await curriculumResponse.json()) as {
    course: { published_lessons: number }
    units: Array<{
      slug: string
      lessons: Array<{ number: number; title: string }>
      review?: { slug: string; question_count: number; source_kind: string } | null
    }>
  }
  expect(curriculum.course.published_lessons).toBe(52)
  expect(curriculum.units).toHaveLength(10)
  expect(curriculum.units[5]).toMatchObject({
    slug: '26-30',
    lessons: [
      { number: 26, title: 'This Game Is Fun!' },
      { number: 27, title: "I Can't Come In" },
      { number: 28, title: 'I Passed It!' },
      { number: 29, title: 'A Long Time Ago' },
      { number: 30, title: 'Rolling on the River' },
    ],
    review: {
      slug: 'checkpoint-26-30-level-1',
      question_count: 6,
      source_kind: 'authorial',
    },
  })

  const expected = [
    [26, 'Ought to + passado irregular', 'fazer associações'],
    [27, 'Passado irregular + saúde e conselhos', 'analisar informações'],
    [28, 'Imperativos + was e were', 'falar consigo mesmo'],
    [29, 'Simple past + adjetivos e infinitivos', 'personalizar'],
    [30, 'Comparativos, superlativos + much e many', 'fazer inferências'],
  ] as const
  for (const [number, grammarTag, learningStrategy] of expected) {
    const response = await request.get(`/api/courses/${LEVEL_1_SLUG}/lessons/${number}`)
    expect(response.ok()).toBeTruthy()
    const lesson = (await response.json()) as {
      grammar_tag: string
      goals: unknown[]
      grammar_blocks: unknown[]
      phrases: unknown[]
      vocab: unknown[]
      pronunciation: unknown[]
      versions: Array<{ learning_strategy: string }>
      exercises: Array<{ skill: string }>
      media: Array<{ cues: unknown[] }>
      writing_prompts: unknown[]
    }
    expect(lesson.grammar_tag).toBe(grammarTag)
    expect(lesson.versions[0]?.learning_strategy).toBe(learningStrategy)
    expect(lesson.goals).toHaveLength(4)
    expect(lesson.grammar_blocks).toHaveLength(3)
    expect(lesson.phrases).toHaveLength(5)
    expect(lesson.vocab).toHaveLength(10)
    expect(lesson.pronunciation).toHaveLength(3)
    expect(lesson.exercises).toHaveLength(8)
    expect(lesson.exercises.filter((exercise) => exercise.skill === 'listening')).toHaveLength(4)
    expect(lesson.media).toHaveLength(1)
    expect(lesson.media[0]?.cues).toHaveLength(5)
    expect(lesson.writing_prompts).toHaveLength(1)
  }

  await criarConta(page, 'Unidade Level 1 Sprint 36')
  await page.goto(unitPath('26-30'))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 26–30' })).toBeVisible()
  const lessons = page.locator('.course-unit-lessons')
  await expect(lessons.locator('a[href*="/aulas/"]')).toHaveCount(5)
  for (const [number, title] of [
    [26, 'This Game Is Fun!'],
    [27, "I Can't Come In"],
    [28, 'I Passed It!'],
    [29, 'A Long Time Ago'],
    [30, 'Rolling on the River'],
  ] as const) {
    await expect(lessons.getByRole('link', { name: new RegExp(escapeRegex(title)) })).toHaveAttribute(
      'href',
      lessonPath(number),
    )
  }
  await expect(
    page.getByRole('main').getByRole('link', { name: /Fechamento 26–30/ }),
  ).toHaveAttribute('href', courseReviewPath('26-30'))

  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))
  await page.goto(courseReviewPath('26-30'))
  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(provenance.getByText('Origem', { exact: true })).toBeVisible()
  await expect(provenance.getByText('Base curricular', { exact: true })).toHaveCount(0)
  await expect(provenance.getByText('Fechamento autoral do Aulas de Inglês')).toBeVisible()
  await expect(provenance.locator('a')).toHaveCount(0)
  await expect(provenance).toContainText('revisão oficial 25–29')
  await expect(provenance).toContainText('revisão oficial 30–34')
  const checkpointAudio = page.locator('audio[aria-label="Conversa da Aula 30 — Level 1"]')
  await expect(checkpointAudio).toBeVisible()
  await expect(checkpointAudio.locator('source')).toHaveAttribute('src', /voa-audio\.voanews\.eu/)
  await expect(page.getByRole('link', { name: 'Rever Aula 30' })).toHaveAttribute(
    'href',
    lessonPath(30),
  )
})

test('fechamento autoral 31–40 cobre cada aula e passa a integrar o certificado', async ({
  page,
  request,
}) => {
  const curriculumResponse = await request.get(`/api/courses/${LEVEL_1_SLUG}/curriculum`)
  expect(curriculumResponse.ok()).toBeTruthy()
  const curriculum = (await curriculumResponse.json()) as {
    units: Array<{
      slug: string
      review?: {
        slug: string
        title: string
        question_count: number
        source_kind: string
        review_lesson_number: number
      } | null
    }>
  }
  const unit = curriculum.units.find(({ slug }) => slug === '31-40')
  expect(unit?.review).toMatchObject({
    slug: 'checkpoint-31-40-level-1',
    title: 'Fechamento 31–40',
    question_count: 10,
    source_kind: 'authorial',
    review_lesson_number: 40,
  })

  await criarConta(page, 'Fechamento 31–40 E2E')
  await page.goto(unitPath('31-40'))
  await expect(
    page.getByRole('main').getByRole('link', { name: /Fechamento 31–40/ }),
  ).toHaveAttribute('href', courseReviewPath('31-40'))

  await page.goto(lessonPath(40))
  await expect(page.getByRole('link', { name: 'Fechamento 31–40 →' })).toHaveAttribute(
    'href',
    courseReviewPath('31-40'),
  )

  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))
  const checkpointPath = courseReviewPath('31-40')
  await page.goto(checkpointPath)
  await expect(page.getByRole('heading', { level: 1, name: 'Fechamento 31–40' })).toBeVisible()

  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(provenance.getByText('Origem', { exact: true })).toBeVisible()
  await expect(provenance.getByText('Base curricular', { exact: true })).toHaveCount(0)
  await expect(provenance.getByText('Fechamento autoral do Aulas de Inglês')).toBeVisible()
  await expect(provenance.locator('a')).toHaveCount(0)
  await expect(provenance).toContainText('30–34, 35–39 e 40–44')
  await expect(provenance).toContainText('inteiramente autoral')

  const checkpointAudio = page.locator('audio[aria-label="Conversa da Aula 40"]')
  await expect(checkpointAudio).toBeVisible()
  await expect(checkpointAudio.locator('source')).toHaveAttribute('src', /voa-audio\.voanews\.eu/)
  await expect(page.getByRole('link', { name: 'Rever Aula 40' })).toHaveAttribute(
    'href',
    lessonPath(40),
  )

  const form = page.locator('.checkpoint-form')
  await expect(form.getByRole('group')).toHaveCount(10)
  await expect(form.getByText('0/10 respondidas')).toBeVisible()
  for (const answer of [
    'faster than',
    'us',
    'pitcher',
    'might',
    'I bought two loaves of bread.',
    'are; under',
    'mine',
    'the best',
    'imperfect',
    'More loudly and more seriously.',
  ]) {
    await form.getByRole('radio', { name: answer, exact: true }).check()
  }
  await expect(form.getByText('10/10 respondidas')).toBeVisible()

  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        '/api/courses/voa-level-1/units/31-40/review/attempts' &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await form.getByRole('button', { name: 'Concluir checkpoint' }).click()
  expect((await saved).status()).toBe(201)

  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 10 de 10 questões (100%).')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Continuar na Aula 41' })).toHaveAttribute(
    'href',
    lessonPath(41),
  )
  await page.reload()
  await expect(page.getByText('Você acertou 10 de 10 questões (100%).')).toBeVisible()
  await expect(page.locator('.checkpoint-form')).toHaveCount(0)
})

test('concluir somente a Aula 52 não libera certificado nem completa outras unidades', async ({
  request,
}) => {
  const register = await request.post('/api/auth/register', {
    data: {
      email: emailUnico(),
      password: SENHA,
      display_name: 'Conclusão Sprint 24 E2E',
    },
  })
  expect(register.status()).toBe(201)
  const token = (await register.json()).access_token as string
  const headers = { Authorization: `Bearer ${token}` }

  const initialResponse = await request.get(`/api/courses/${LEVEL_1_SLUG}/completion`, {
    headers,
  })
  expect(initialResponse.ok()).toBeTruthy()
  expect(initialResponse.headers()['cache-control']).toBe('private, no-store')
  const initial = await initialResponse.json()
  expect(initial).toMatchObject({
    progress: {
      published_lessons: 52,
      viewed_lessons: 0,
      completed_lessons: 0,
      completion_percent: 0,
      status: 'not_started',
    },
    checkpoints: { published: 10, current_completed: 0 },
    certificate: {
      eligible: false,
      required_lessons: 52,
      required_checkpoints: 10,
      automatic_download: false,
    },
    next_course: {
      slug: LEVEL_2_SLUG,
      level: '2',
      status: 'published',
      recommended: true,
      required: false,
      href: coursePath(LEVEL_2_SLUG),
    },
  })
  expect(initial.incomplete_units.map((unit: { slug: string }) => unit.slug)).toEqual([
    '1-5',
    '6-10',
    '11-15',
    '16-20',
    '21-25',
    '26-30',
    '31-40',
    '40-44',
    '45-49',
    '50-52',
  ])
  expect(initial.skills).toHaveLength(4)
  expect(initial.skills.every((skill: { status: string }) => skill.status === 'insufficient'))
    .toBeTruthy()

  const markOnlyLast = await request.put(
    `/api/courses/${LEVEL_1_SLUG}/lessons/52/studied`,
    { headers },
  )
  expect(markOnlyLast.status()).toBe(204)

  const after = await (
    await request.get(`/api/courses/${LEVEL_1_SLUG}/completion`, { headers })
  ).json()
  expect(after.progress).toMatchObject({
    published_lessons: 52,
    viewed_lessons: 1,
    completed_lessons: 1,
    status: 'in_progress',
  })
  expect(after.certificate).toMatchObject({ eligible: false, automatic_download: false })
  expect(after.incomplete_units).toHaveLength(10)
  expect(
    after.incomplete_units.find((unit: { slug: string }) => unit.slug === '50-52'),
  ).toMatchObject({ published_lessons: 3, viewed_lessons: 1, completed_lessons: 1 })
})

test('Sprint 23 preserva fronteiras de unidade e avaliação escopada a 45–49', async ({
  page,
}) => {
  await criarConta(page, 'Fronteiras Sprint 23 E2E')

  await page.goto(lessonPath(45))
  await expect(page.getByRole('heading', { name: 'This Land is Your Land' })).toBeVisible()
  await expect(page.getByRole('link', { name: '← Checkpoint 40–44' })).toHaveAttribute(
    'href',
    courseReviewPath('40-44'),
  )

  await page.goto(lessonPath(49))
  await expect(page.getByRole('heading', { name: 'Operation Spy!' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Checkpoint 45–49 →' })).toHaveAttribute(
    'href',
    courseReviewPath('45-49'),
  )

  await page.goto(assessmentPath('45-49'))
  await expect(page.getByRole('heading', { level: 1, name: 'Avaliação da unidade' })).toBeVisible()
  await expect(
    page.getByText(/Avaliação · Let's Learn English — Level 1 · Aulas 45–49/),
  ).toBeVisible()
  await expect(page.locator('.origem')).toHaveText([
    'Aula 45',
    'Aula 46',
    'Aula 47',
    'Aula 48',
    'Aula 49',
  ])
  await expect(page.locator('.origem', { hasText: 'Aula 44' })).toHaveCount(0)
  await expect(page.locator('.origem', { hasText: 'Aula 31' })).toHaveCount(0)
})

test('checkpoint 45–49 corrige seis questões, explica pistas temporais e persiste', async ({
  page,
}) => {
  await criarConta(page, 'Checkpoint Sprint 23 E2E')
  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))

  const checkpointPath = courseReviewPath('45-49')
  await page.goto(checkpointPath)
  await expect(page).toHaveURL(new RegExp(`${checkpointPath}$`))
  await expect(page.getByRole('heading', { level: 1, name: 'Checkpoint 45–49' })).toBeVisible()

  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(
    provenance.getByRole('link', { name: /VOA Learning English — Review of Lessons 45–49/ }),
  ).toBeVisible()
  await expect(provenance.getByText('Conteúdo autoral do projeto')).toBeVisible()

  await expect(page.getByRole('heading', { name: 'Conversa da Aula 49' })).toBeVisible()
  const checkpointAudio = page.locator('audio[aria-label="Conversa da Aula 49"]')
  await expect(checkpointAudio).toBeVisible()
  await expect(checkpointAudio.locator('source')).toHaveAttribute('src', /voa-audio\.voanews\.eu/)
  await expect(page.getByRole('link', { name: 'Rever Aula 49' })).toHaveAttribute(
    'href',
    lessonPath(49),
  )

  const form = page.locator('.checkpoint-form')
  await expect(form.getByRole('group')).toHaveCount(6)
  for (const answer of [
    'will be driving',
    'May I borrow your scissors?',
    'Pete is fixing the car now, but he was studying last night.',
    'I have lived here for three years.',
    'She has never cracked one, is still trying, and then has cracked it.',
    'Tomorrow we will be traveling; now we are packing; we have never visited that city.',
  ]) {
    await form.getByRole('radio', { name: answer, exact: true }).check()
  }

  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        '/api/courses/voa-level-1/units/45-49/review/attempts' &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await form.getByRole('button', { name: 'Concluir checkpoint' }).click()
  expect((await saved).status()).toBe(201)

  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.getByText(/at this time tomorrow.*ação que estará em andamento/i)).toBeVisible()
  await expect(page.getByText(/For three years.*duração que chega ao presente/i)).toBeVisible()

  await page.reload()
  await expect(page).toHaveURL(new RegExp(`${checkpointPath}$`))
  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.locator('.checkpoint-form')).toHaveCount(0)
})

test('Sprint 24 preserva fronteiras da unidade final e expõe o fechamento no mapa', async ({
  page,
}) => {
  await criarConta(page, 'Fronteiras Sprint 24 E2E')

  await page.goto(lessonPath(50))
  await expect(page.getByRole('heading', { name: 'Back to School' })).toBeVisible()
  await expect(page.getByRole('link', { name: '← Checkpoint 45–49' })).toHaveAttribute(
    'href',
    courseReviewPath('45-49'),
  )

  await page.goto(lessonPath(52))
  await expect(page.getByRole('heading', { name: 'Taking Chances' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Checkpoint 50–52 →' })).toHaveAttribute(
    'href',
    courseReviewPath('50-52'),
  )

  await page.goto(coursePath(LEVEL_1_SLUG))
  await expect(page.getByRole('link', { name: 'Ver meu fechamento' })).toHaveAttribute(
    'href',
    courseCompletionPath(),
  )
})

test('checkpoint 50–52 encerra a revisão oficial e conduz à conclusão', async ({ page }) => {
  await criarConta(page, 'Checkpoint Sprint 24 E2E')
  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))

  const checkpointPath = courseReviewPath('50-52')
  await page.goto(checkpointPath)
  await expect(page.getByRole('heading', { level: 1, name: 'Checkpoint 50–52' })).toBeVisible()

  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(
    provenance.getByRole('link', { name: /VOA Learning English — Review of Lessons 50–52/ }),
  ).toBeVisible()
  await expect(provenance.getByText('Conteúdo autoral do projeto')).toBeVisible()
  await expect(provenance).toContainText('O certificado e mídias de terceiros não foram incorporados')

  const checkpointAudio = page.locator('audio[aria-label="Conversa da Aula 52"]')
  await expect(checkpointAudio).toBeVisible()
  await expect(checkpointAudio.locator('source')).toHaveAttribute('src', /voa-audio\.voanews\.eu/)
  expect(await checkpointAudio.getAttribute('autoplay')).toBeNull()
  await expect(page.getByRole('link', { name: 'Rever Aula 52' })).toHaveAttribute(
    'href',
    lessonPath(52),
  )

  const form = page.locator('.checkpoint-form')
  await expect(form.getByRole('group')).toHaveCount(6)
  for (const answer of [
    'has been writing',
    'We have been waiting for ten minutes, and he has been studying since 2015.',
    'loves · to challenge',
    "I've been training for an hour; I've just found a new goal.",
    'Sometimes she succeeded, sometimes she failed, but she will never stop trying.',
    'She has been training for a month; her career has taken off; next year she will be acting in movies.',
  ]) {
    await form.getByRole('radio', { name: answer, exact: true }).check()
  }

  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        '/api/courses/voa-level-1/units/50-52/review/attempts' &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await form.getByRole('button', { name: 'Concluir checkpoint' }).click()
  expect((await saved).status()).toBe(201)

  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.getByText(/since last night.*continua no presente/i)).toBeVisible()
  const finalFeedback = page
    .getByRole('status', { name: 'Bloco consolidado' })
    .getByRole('listitem')
    .filter({ hasText: 'has taken off' })
  await expect(finalFeedback).toContainText('resultado atual da carreira')
  await expect(finalFeedback).toContainText('has taken off')

  await page.reload()
  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.locator('.checkpoint-form')).toHaveCount(0)
  const completion = page.getByRole('link', { name: 'Ver progresso do curso' })
  await expect(completion).toHaveAttribute('href', courseCompletionPath())
  await completion.click()
  await expect(page).toHaveURL(new RegExp(`${courseCompletionPath()}$`))
  await expect(
    page.getByRole('heading', { level: 1, name: /Conclusão de Let's Learn English — Level 1/ }),
  ).toBeFocused()
  await expect(page.getByText('Em andamento', { exact: true })).toBeVisible()
})
