import { expect, test } from '@playwright/test'

import {
  escapeRegex,
  LEVEL_1_SLUG,
  LEVEL_2_SLUG,
  coursePath,
  lessonPath,
  courseReviewPath,
  unitPath,
  studyPath,
  criarConta,
} from '../journey-helpers'

test('sem sessão, a aplicação pede login', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()
  // Rota interna também cai no login.
  await page.goto('/revisar')
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()
})

test('rotas legadas redirecionam ao Level 1 e preservam etapa, busca e fragmento', async ({
  page,
}) => {
  await criarConta(page, 'Compatibilidade E2E')

  await page.goto('/aulas/31?origem=e2e#objetivos')
  await expect(page).toHaveURL(
    new RegExp(`${lessonPath(31)}\\?origem=e2e#objetivos$`),
  )

  for (const step of ['preparar', 'assistir', 'estudar', 'praticar', 'revisar'] as const) {
    await page.goto(`/aulas/31/estudar/${step}?origem=e2e#etapa`)
    await expect(page).toHaveURL(
      new RegExp(`${studyPath(31, step)}\\?origem=e2e#etapa$`),
    )
  }
})

test('Sprints anteriores seguem publicadas após o fechamento do Level 2', async ({
  page,
  request,
}) => {
  const curriculumResponse = await request.get(`/api/courses/${LEVEL_2_SLUG}/curriculum`)
  expect(curriculumResponse.ok()).toBeTruthy()
  const curriculum = (await curriculumResponse.json()) as {
    course: { status: string; published_lessons: number; total_lessons: number }
    units: Array<{
      slug: string
      status: string
      published_lessons: number
      lessons: Array<{ number: number; title: string }>
      review?: { slug: string; question_count: number } | null
    }>
  }
  expect(curriculum.course).toMatchObject({
    status: 'published',
    published_lessons: 30,
    total_lessons: 30,
  })
  expect(curriculum.units[0]).toMatchObject({
    slug: '1-5',
    status: 'published',
    published_lessons: 5,
    review: { slug: 'checkpoint-1-5', question_count: 6 },
  })
  expect(curriculum.units[0]?.lessons.map((lesson) => lesson.number)).toEqual([1, 2, 3, 4, 5])
  expect(curriculum.units[1]).toMatchObject({
    slug: '6-10',
    status: 'published',
    published_lessons: 5,
    review: { slug: 'checkpoint-6-10', question_count: 6 },
  })
  expect(curriculum.units[1]?.lessons.map((lesson) => lesson.number)).toEqual([6, 7, 8, 9, 10])
  expect(curriculum.units[2]).toMatchObject({
    slug: '11-15',
    status: 'published',
    published_lessons: 5,
    review: { slug: 'checkpoint-11-15', question_count: 6 },
  })
  expect(curriculum.units[2]?.lessons.map((lesson) => lesson.number)).toEqual([11, 12, 13, 14, 15])
  expect(curriculum.units[3]).toMatchObject({
    slug: '16-20',
    status: 'published',
    published_lessons: 5,
    review: { slug: 'checkpoint-16-20', question_count: 6 },
  })
  expect(curriculum.units[3]?.lessons.map((lesson) => lesson.number)).toEqual([16, 17, 18, 19, 20])
  expect(curriculum.units[4]).toMatchObject({
    slug: '21-25',
    status: 'published',
    published_lessons: 5,
    review: { slug: 'checkpoint-21-25', question_count: 6 },
  })
  expect(curriculum.units[4]?.lessons.map((lesson) => lesson.number)).toEqual([21, 22, 23, 24, 25])
  // Sprint 30: o Level 2 fecha. Nenhuma unidade planejada resta, e o último
  // bloco traz um fechamento AUTORAL — a VOA não publica review das 26–30.
  expect(curriculum.units[5]).toMatchObject({
    slug: '26-30',
    status: 'published',
    published_lessons: 5,
    review: { slug: 'checkpoint-26-30', question_count: 6, source_kind: 'authorial' },
  })
  expect(curriculum.units[5]?.lessons.map((lesson) => lesson.number)).toEqual([26, 27, 28, 29, 30])
  expect(curriculum.units).toHaveLength(6)
  expect(curriculum.units.at(-1)?.review).toMatchObject({
    slug: 'checkpoint-26-30',
    source_kind: 'authorial',
  })

  await criarConta(page, 'Catálogo E2E')
  await page.goto('/cursos')

  await expect(page.getByRole('heading', { name: 'Cursos de inglês' })).toBeVisible()
  const level1Card = page
    .getByRole('article')
    .filter({ has: page.getByRole('heading', { name: "Let's Learn English — Level 1" }) })
  const level2Card = page
    .getByRole('article')
    .filter({ has: page.getByRole('heading', { name: "Let's Learn English — Level 2" }) })

  await expect(level1Card.getByText('1 · Iniciante')).toBeVisible()
  await expect(level1Card.getByRole('link', { name: 'Ver unidades' })).toHaveAttribute(
    'href',
    coursePath(LEVEL_1_SLUG),
  )
  await expect(level2Card.getByText('2 · Intermediário')).toBeVisible()
  await expect(level2Card.getByText('30/30', { exact: true })).toBeVisible()
  await expect(level2Card.getByText('Publicado', { exact: true })).toBeVisible()

  await level2Card.getByRole('link', { name: 'Ver unidades' }).click()
  await expect(page).toHaveURL(new RegExp(`${coursePath(LEVEL_2_SLUG)}$`))
  await expect(page.getByRole('heading', { name: 'Mapa do curso' })).toBeVisible()
  await expect(page.getByText(/Level 2 · Intermediário · VOA Learning English/)).toBeVisible()
  const unitCards = page.locator('.unit-card-grid')
  // Quatro unidades publicadas e navegáveis; as duas últimas seguem em preparação.
  await expect(unitCards.locator('a')).toHaveCount(6)
  await expect(unitCards.getByText('Em preparação', { exact: true })).toHaveCount(0)
  await expect(unitCards.locator('a', { hasText: 'Aulas 26–30' })).toHaveCount(1)

  await unitCards.locator('a', { hasText: 'Aulas 1–5' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 1–5' })).toBeVisible()
  await expect(page.locator('.course-unit-lessons a[href*="/aulas/"]')).toHaveCount(5)
  await expect(
    page.getByRole('main').getByRole('link', { name: /Checkpoint 1–5/ }),
  ).toHaveAttribute('href', courseReviewPath('1-5', LEVEL_2_SLUG))

  await page.goto(unitPath('6-10', LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 6–10' })).toBeVisible()
  const lessons610 = page.locator('.course-unit-lessons')
  await expect(lessons610.locator('a[href*="/aulas/"]')).toHaveCount(5)
  // Escopado à lista da unidade: a trilha lateral também linka a mesma aula,
  // e sem escopo o locator casa com dois elementos.
  await expect(lessons610.getByRole('link', { name: /The Best Barbecue/ })).toHaveAttribute(
    'href',
    lessonPath(8, LEVEL_2_SLUG),
  )
  await expect(
    page.getByRole('main').getByRole('link', { name: /Checkpoint 6–10/ }),
  ).toHaveAttribute('href', courseReviewPath('6-10', LEVEL_2_SLUG))
})

test('Sprint 28 publica a unidade 16–20 e mantém as fronteiras curriculares', async ({
  page,
}) => {
  await criarConta(page, 'Unidade Level 2 Sprint 28')

  await page.goto(unitPath('16-20', LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 16–20' })).toBeVisible()
  const lessons = page.locator('.course-unit-lessons')
  await expect(lessons.locator('a[href*="/aulas/"]')).toHaveCount(5)
  for (const [number, title] of [
    [16, 'Find Your Joy!'],
    [17, 'Flour Baby, Part 1'],
    [18, 'Flour Baby, Part 2'],
    [19, 'Movie Night'],
    [20, 'The Test Drive'],
  ] as const) {
    await expect(lessons.getByRole('link', { name: new RegExp(escapeRegex(title)) })).toHaveAttribute(
      'href',
      lessonPath(number, LEVEL_2_SLUG),
    )
  }

  // As duas partes de Flour Baby são aulas independentes.
  await page.goto(lessonPath(17, LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Flour Baby, Part 1' })).toBeVisible()
  await page.goto(lessonPath(18, LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Flour Baby, Part 2' })).toBeVisible()

  // O bloco seguinte continua indisponível, sem link morto.
  await expect(page.getByRole('link', { name: /Aulas 26–30/ })).toHaveCount(0)
})

test('Sprint 29 publica a unidade 21–25 e mantém as fronteiras curriculares', async ({
  page,
}) => {
  await criarConta(page, 'Unidade Level 2 Sprint 29')

  await page.goto(unitPath('21-25', LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 21–25' })).toBeVisible()
  const lessons = page.locator('.course-unit-lessons')
  await expect(lessons.locator('a[href*="/aulas/"]')).toHaveCount(5)
  for (const [number, title] of [
    [21, 'Trash to Treasure, Part 1'],
    [22, 'Trash to Treasure, Part 2'],
    [23, 'Rock Star'],
    [24, 'I Feel Super!'],
    [25, 'Only Human'],
  ] as const) {
    await expect(lessons.getByRole('link', { name: new RegExp(escapeRegex(title)) })).toHaveAttribute(
      'href',
      lessonPath(number, LEVEL_2_SLUG),
    )
  }

  // Trash to Treasure Part 1 e Part 2 continuam aulas independentes.
  await page.goto(lessonPath(21, LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Trash to Treasure, Part 1' })).toBeVisible()
  await page.goto(lessonPath(22, LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Trash to Treasure, Part 2' })).toBeVisible()

  // A página de uma unidade não linka a unidade seguinte — isso não mudou
  // com a Sprint 30, que apenas publicou o bloco 26–30.
  await expect(page.getByRole('link', { name: /Aulas 26–30/ })).toHaveCount(0)
})

test('Sprint 30 fecha o Level 2 e rotula o fechamento como autoral', async ({ page }) => {
  await criarConta(page, 'Fechamento Level 2')

  await page.goto(unitPath('26-30', LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 26–30' })).toBeVisible()
  const lessons = page.locator('.course-unit-lessons')
  await expect(lessons.locator('a[href*="/aulas/"]')).toHaveCount(5)
  for (const [number, title] of [
    [26, 'Look-alikes'],
    [27, 'Fish out of Water'],
    [28, 'For the Birds'],
    [29, "Where There's Smoke..."],
    [30, 'Dream a Little Dream'],
  ] as const) {
    await expect(lessons.getByRole('link', { name: new RegExp(escapeRegex(title)) })).toHaveAttribute(
      'href',
      lessonPath(number, LEVEL_2_SLUG),
    )
  }

  // O fechamento é autoral: a interface não pode chamá-lo de base curricular
  // nem oferecer link para um review oficial que não existe.
  await page.goto(courseReviewPath('26-30', LEVEL_2_SLUG))
  const origem = page.locator('.checkpoint-provenance')
  await expect(origem.getByText('Origem', { exact: true })).toBeVisible()
  await expect(origem.getByText('Base curricular', { exact: true })).toHaveCount(0)
  await expect(origem.getByText('Fechamento autoral do Aulas de Inglês')).toBeVisible()
  await expect(origem.locator('a')).toHaveCount(0)
  await expect(origem.getByText(/não publica review das Aulas 26–30/)).toBeVisible()
  await expect(origem.getByText(/não confere certificação/)).toBeVisible()
})

test('Sprint 27 publica a unidade 11–15 e preserva as fronteiras curriculares', async ({
  page,
}) => {
  await criarConta(page, 'Unidade Level 2 Sprint 27')

  await page.goto(unitPath('11-15', LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Aulas 11–15' })).toBeVisible()
  const lessons = page.locator('.course-unit-lessons')
  await expect(lessons.locator('a[href*="/aulas/"]')).toHaveCount(5)
  for (const [number, title] of [
    [11, 'The Big Snow'],
    [12, 'Run! Bees!'],
    [13, 'Save the Bees!'],
    [14, 'Made for Each Other'],
    [15, 'Before and After'],
  ] as const) {
    await expect(lessons.getByRole('link', { name: new RegExp(title) })).toHaveAttribute(
      'href',
      lessonPath(number, LEVEL_2_SLUG),
    )
  }
  await expect(
    page.getByRole('main').getByRole('link', { name: /Checkpoint 11–15/ }),
  ).toHaveAttribute('href', courseReviewPath('11-15', LEVEL_2_SLUG))

  await page.goto(lessonPath(10, LEVEL_2_SLUG))
  await expect(page.getByRole('link', { name: 'Checkpoint 6–10 →' })).toHaveAttribute(
    'href',
    courseReviewPath('6-10', LEVEL_2_SLUG),
  )

  await page.goto(lessonPath(11, LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'The Big Snow' })).toBeVisible()
  await expect(page.getByRole('link', { name: '← Checkpoint 6–10' })).toHaveAttribute(
    'href',
    courseReviewPath('6-10', LEVEL_2_SLUG),
  )
  await expect(page.getByRole('link', { name: 'Aula 12 →' })).toHaveAttribute(
    'href',
    lessonPath(12, LEVEL_2_SLUG),
  )

  await page.goto(lessonPath(15, LEVEL_2_SLUG))
  await expect(page.getByRole('heading', { level: 1, name: 'Before and After' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Checkpoint 11–15 →' })).toHaveAttribute(
    'href',
    courseReviewPath('11-15', LEVEL_2_SLUG),
  )
  await expect(page.getByRole('link', { name: 'Aula 16 →' })).toHaveCount(0)
})
