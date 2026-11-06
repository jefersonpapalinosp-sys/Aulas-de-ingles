import { expect, test } from '@playwright/test'

import AxeBuilder from '@axe-core/playwright'

import {
  escapeRegex,
  LEVEL_1_SLUG,
  lessonPath,
  courseReviewPath,
  unitPath,
  criarConta,
} from '../journey-helpers'

test('checkpoint 40–44 corrige seis questões e restaura o resultado salvo', async ({ page }) => {
  await criarConta(page, 'Checkpoint Sprint 22 E2E')

  // O teste confirma a presença e os metadados do player, sem depender de
  // baixar ou reproduzir o MP3 externo da VOA.
  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))
  const checkpointPath = courseReviewPath('40-44')
  await page.goto(checkpointPath)

  await expect(page).toHaveURL(new RegExp(`${checkpointPath}$`))
  await expect(page.getByRole('heading', { level: 1, name: 'Checkpoint 40–44' })).toBeVisible()

  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(provenance).toBeVisible()
  await expect(
    provenance.getByRole('link', { name: /VOA Learning English — Review Lessons 40–44/ }),
  ).toBeVisible()
  await expect(provenance.getByText('Conteúdo autoral do projeto')).toBeVisible()
  await expect(provenance).toContainText(
    'A seleção de competências acompanha a revisão oficial da VOA',
  )

  await expect(page.getByRole('heading', { name: 'Conversa da Aula 40' })).toBeVisible()
  const checkpointAudio = page.locator('audio[aria-label="Conversa da Aula 40"]')
  await expect(checkpointAudio).toBeVisible()
  await expect(checkpointAudio.locator('source')).toHaveAttribute(
    'src',
    /voa-audio\.voanews\.eu/,
  )
  await expect(page.getByRole('link', { name: 'Rever Aula 40' })).toHaveAttribute(
    'href',
    lessonPath(40),
  )

  const accessibility = await new AxeBuilder({ page })
    .include('.checkpoint-page')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(
    accessibility.violations.filter(
      ({ impact }) => impact === 'serious' || impact === 'critical',
    ),
  ).toEqual([])

  const form = page.locator('.checkpoint-form')
  await expect(form.getByRole('group')).toHaveCount(6)
  await expect(form.getByText('0/6 respondidas')).toBeVisible()

  for (const answer of [
    'uma árvore',
    'will see',
    'Anna hurt herself.',
    'Would you be able to help me?',
    "You don't have to buy bread.",
    'will succeed · yourself · must',
  ]) {
    await form.getByRole('radio', { name: answer, exact: true }).check()
  }

  await expect(form.getByText('6/6 respondidas')).toBeVisible()
  await expect(form.getByRole('progressbar', { name: 'Questões respondidas' })).toHaveAttribute(
    'aria-valuenow',
    '6',
  )

  const saved = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        '/api/courses/voa-level-1/units/40-44/review/attempts' &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await form.getByRole('button', { name: 'Concluir checkpoint' }).click()
  expect((await saved).status()).toBe(201)

  await expect(page.getByText('Resultado salvo')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.getByLabel('100 por cento')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Continuar na Aula 45' })).toHaveAttribute(
    'href',
    lessonPath(45),
  )

  await page.reload()
  await expect(page).toHaveURL(new RegExp(`${checkpointPath}$`))
  await expect(page.getByText('Resultado salvo')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Bloco consolidado' })).toBeVisible()
  await expect(page.getByText('Você acertou 6 de 6 questões (100%).')).toBeVisible()
  await expect(page.locator('.checkpoint-form')).toHaveCount(0)
})

test('Sprint 23 publica a unidade 45–49 no catálogo sem alongar a trilha', async ({
  page,
  request,
}) => {
  const curriculumResponse = await request.get(`/api/courses/${LEVEL_1_SLUG}/curriculum`)
  expect(curriculumResponse.ok()).toBeTruthy()
  const curriculum = (await curriculumResponse.json()) as {
    units: Array<{
      slug: string
      published_lessons: number
      lessons: Array<{ number: number }>
      review?: { title: string; question_count: number } | null
    }>
  }
  const unit = curriculum.units.find((candidate) => candidate.slug === '45-49')
  expect(unit).toBeDefined()
  expect(unit?.published_lessons).toBe(5)
  expect(unit?.lessons.map((lesson) => lesson.number)).toEqual([45, 46, 47, 48, 49])
  expect(unit?.review).toMatchObject({ title: 'Checkpoint 45–49', question_count: 6 })

  await criarConta(page, 'Unidade 45–49 E2E')
  await page.goto('/cursos')
  const level1Card = page
    .getByRole('article')
    .filter({ has: page.getByRole('heading', { name: "Let's Learn English — Level 1" }) })
  await expect(level1Card.getByText('52/52', { exact: true })).toBeVisible()

  await page.goto(unitPath('45-49'))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 45–49' })).toBeVisible()
  await expect(page.getByText('5 aulas disponíveis e um checkpoint de consolidação')).toBeVisible()
  const unitItems = page.locator('.course-unit-lessons')
  await expect(unitItems.locator('a[href*="/aulas/"]')).toHaveCount(5)
  await expect(unitItems.getByText('This Land is Your Land', { exact: true })).toBeVisible()
  await expect(unitItems.getByText('Operation Spy!', { exact: true })).toBeVisible()
  await expect(unitItems.getByRole('link', { name: /Checkpoint 45–49/ })).toHaveAttribute(
    'href',
    courseReviewPath('45-49'),
  )
})

test('Sprint 24 publica as Aulas 50–52 e o checkpoint final sem inventar transcrições', async ({
  request,
}) => {
  const curriculumResponse = await request.get(`/api/courses/${LEVEL_1_SLUG}/curriculum`)
  expect(curriculumResponse.ok()).toBeTruthy()
  const curriculum = (await curriculumResponse.json()) as {
    course: { published_lessons: number }
    units: Array<{
      slug: string
      published_lessons: number
      lessons: Array<{ number: number; title: string }>
      review?: { title: string; question_count: number } | null
    }>
  }
  expect(curriculum.course.published_lessons).toBe(52)
  const unit = curriculum.units.find((candidate) => candidate.slug === '50-52')
  expect(unit).toMatchObject({
    published_lessons: 3,
    lessons: [
      { number: 50, title: 'Back to School' },
      { number: 51, title: 'A Good Habit' },
      { number: 52, title: 'Taking Chances' },
    ],
    review: { title: 'Checkpoint 50–52', question_count: 6 },
  })

  for (const number of [50, 51, 52]) {
    const response = await request.get(`/api/courses/${LEVEL_1_SLUG}/lessons/${number}`)
    expect(response.ok()).toBeTruthy()
    const lesson = (await response.json()) as {
      media: Array<{
        source_url: string
        cues: unknown[]
        transcript: unknown[]
        offline_policy: string
      }>
      exercises: Array<{ skill: string }>
      vocab: unknown[]
    }
    expect(lesson.media).toHaveLength(1)
    expect(lesson.media[0]).toMatchObject({
      source_url: expect.stringContaining('voa-audio.voanews.eu'),
      offline_policy: 'network_only',
      transcript: [],
    })
    expect(lesson.media[0]?.cues).toHaveLength(5)
    expect(lesson.exercises).toHaveLength(8)
    expect(lesson.exercises.filter((exercise) => exercise.skill === 'listening')).toHaveLength(4)
    expect(lesson.vocab).toHaveLength(10)
  }
})

test('Sprint 34 publica as Aulas 16–20 do Level 1 com pacote multimodal completo', async ({
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
  expect(curriculum.units[3]).toMatchObject({
    slug: '16-20',
    lessons: [
      { number: 16, title: 'Where Are You From?' },
      { number: 17, title: 'Are You Free on Friday?' },
      { number: 18, title: 'She Always Does That' },
      { number: 19, title: 'When Do I Start?' },
      { number: 20, title: 'What Can You Do?' },
    ],
    review: {
      slug: 'checkpoint-16-20-level-1',
      question_count: 6,
      source_kind: 'authorial',
    },
  })

  const expected = [
    [16, 'Nacionalidades e idiomas', 'monitorar'],
    [17, 'Futuro com will e going to', 'avaliar'],
    [18, 'Frequência, pronomes objeto e ordinais', 'classificar'],
    [19, 'Which, which one, next e every', 'resumir'],
    [20, "Habilidade com can, can't e cannot", 'identificar problemas'],
  ] as const
  for (const [number, grammarTag, learningStrategy] of expected) {
    const response = await request.get(`/api/courses/${LEVEL_1_SLUG}/lessons/${number}`)
    expect(response.ok()).toBeTruthy()
    const lesson = (await response.json()) as {
      grammar_tag: string
      versions: Array<{ learning_strategy: string }>
      vocab: unknown[]
      exercises: Array<{ skill: string }>
      media: Array<{ cues: unknown[] }>
      writing_prompts: unknown[]
    }
    expect(lesson.grammar_tag).toBe(grammarTag)
    expect(lesson.versions[0]?.learning_strategy).toBe(learningStrategy)
    expect(lesson.vocab).toHaveLength(10)
    expect(lesson.exercises).toHaveLength(8)
    expect(lesson.exercises.filter((exercise) => exercise.skill === 'listening')).toHaveLength(4)
    expect(lesson.media).toHaveLength(1)
    expect(lesson.media[0]?.cues).toHaveLength(5)
    expect(lesson.writing_prompts).toHaveLength(1)
  }

  await criarConta(page, 'Unidade Level 1 Sprint 34')
  await page.goto(unitPath('16-20'))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 16–20' })).toBeVisible()
  const lessons = page.locator('.course-unit-lessons')
  await expect(lessons.locator('a[href*="/aulas/"]')).toHaveCount(5)
  await expect(
    page.getByRole('main').getByRole('link', { name: /Fechamento 16–20/ }),
  ).toHaveAttribute('href', courseReviewPath('16-20'))
})

test('Sprint 35 publica as Aulas 21–25 e identifica o fechamento autoral', async ({
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
  expect(curriculum.units[4]).toMatchObject({
    slug: '21-25',
    lessons: [
      { number: 21, title: 'Can You Come to the Party?' },
      { number: 22, title: 'Next Summer...' },
      { number: 23, title: 'What Do You Want?' },
      { number: 24, title: 'Yesterday Was Amazing!' },
      { number: 25, title: 'Watch Out!' },
    ],
    review: {
      slug: 'checkpoint-21-25-level-1',
      question_count: 6,
      source_kind: 'authorial',
    },
  })

  const expected = [
    [21, "Have to, can e can't em convites", 'cooperar'],
    [22, 'Going to e sequência de planos', 'planejar'],
    [23, 'Want, horas, preços e troco', 'responder'],
    [24, 'Passado regular + festivais e cultura', 'substituir'],
    [25, 'Should, ought to e avisos', 'fazer associações'],
  ] as const
  for (const [number, grammarTag, learningStrategy] of expected) {
    const response = await request.get(`/api/courses/${LEVEL_1_SLUG}/lessons/${number}`)
    expect(response.ok()).toBeTruthy()
    const lesson = (await response.json()) as {
      grammar_tag: string
      versions: Array<{ learning_strategy: string }>
      vocab: unknown[]
      exercises: Array<{ skill: string }>
      media: Array<{ cues: unknown[] }>
      writing_prompts: unknown[]
    }
    expect(lesson.grammar_tag).toBe(grammarTag)
    expect(lesson.versions[0]?.learning_strategy).toBe(learningStrategy)
    expect(lesson.vocab).toHaveLength(10)
    expect(lesson.exercises).toHaveLength(8)
    expect(lesson.exercises.filter((exercise) => exercise.skill === 'listening')).toHaveLength(4)
    expect(lesson.media).toHaveLength(1)
    expect(lesson.media[0]?.cues).toHaveLength(5)
    expect(lesson.writing_prompts).toHaveLength(1)
  }

  await criarConta(page, 'Unidade Level 1 Sprint 35')
  await page.goto(unitPath('21-25'))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 21–25' })).toBeVisible()
  const lessons = page.locator('.course-unit-lessons')
  await expect(lessons.locator('a[href*="/aulas/"]')).toHaveCount(5)
  for (const [number, title] of [
    [21, 'Can You Come to the Party?'],
    [22, 'Next Summer...'],
    [23, 'What Do You Want?'],
    [24, 'Yesterday Was Amazing!'],
    [25, 'Watch Out!'],
  ] as const) {
    await expect(lessons.getByRole('link', { name: new RegExp(escapeRegex(title)) })).toHaveAttribute(
      'href',
      lessonPath(number),
    )
  }
  await expect(
    page.getByRole('main').getByRole('link', { name: /Fechamento 21–25/ }),
  ).toHaveAttribute('href', courseReviewPath('21-25'))

  await page.route('https://voa-audio.voanews.eu/**', (route) => route.abort('blockedbyclient'))
  await page.goto(courseReviewPath('21-25'))
  const provenance = page.getByRole('region', { name: 'Origem do checkpoint' })
  await expect(provenance.getByText('Origem', { exact: true })).toBeVisible()
  await expect(provenance.getByText('Base curricular', { exact: true })).toHaveCount(0)
  await expect(provenance.getByText('Fechamento autoral do Aulas de Inglês')).toBeVisible()
  await expect(provenance.locator('a')).toHaveCount(0)
  await expect(provenance).toContainText('reviews dos blocos 20–24 e 25–29')
  await expect(page.getByRole('heading', { name: /Conversa da Aula 25/ })).toBeVisible()
})
