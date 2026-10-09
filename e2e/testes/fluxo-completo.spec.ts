import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

/**
 * O caminho inteiro, numa sessão só:
 *
 *   registrar → estudar a aula 39 → errar o exercício de vocabulário →
 *   a palavra entra no deck → revisar → progresso atualizado
 *
 * A aula 39 não é arbitrária: é uma das poucas em que a resposta certa de um
 * exercício é, literalmente, um termo do vocabulário (`dishonest`). É o que
 * permite exercitar a semeadura do deck pelo erro.
 */

import type { Locator, Page } from '@playwright/test'

function emailUnico() {
  return `e2e-${Date.now()}-${Math.floor(Math.random() * 1000)}@exemplo.com`
}

const SENHA = 'senha-bem-grande'
const LEVEL_1_SLUG = 'voa-level-1'
const LEVEL_2_SLUG = 'voa-level-2'

function coursePath(courseSlug: string): string {
  return `/cursos/${courseSlug}`
}

function courseCompletionPath(courseSlug = LEVEL_1_SLUG): string {
  return `${coursePath(courseSlug)}/conclusao`
}

function lessonPath(lessonNumber: number, courseSlug = LEVEL_1_SLUG): string {
  return `${coursePath(courseSlug)}/aulas/${lessonNumber}`
}

function practicePath(lessonNumber: number, courseSlug = LEVEL_1_SLUG): string {
  return `${lessonPath(lessonNumber, courseSlug)}/exercicios`
}

function courseReviewPath(unitSlug: string, courseSlug = LEVEL_1_SLUG): string {
  return `${coursePath(courseSlug)}/unidades/${unitSlug}/checkpoint`
}

function unitPath(unitSlug: string, courseSlug = LEVEL_1_SLUG): string {
  return `${coursePath(courseSlug)}/unidades/${unitSlug}`
}

function assessmentPath(unitSlug: string, courseSlug = LEVEL_1_SLUG): string {
  return `${unitPath(unitSlug, courseSlug)}/avaliacao`
}

function studyPath(
  lessonNumber: number,
  step?: 'preparar' | 'assistir' | 'estudar' | 'praticar' | 'revisar',
  courseSlug = LEVEL_1_SLUG,
): string {
  const base = `${lessonPath(lessonNumber, courseSlug)}/estudar`
  return step ? `${base}/${step}` : base
}

async function expectNoHorizontalScroll(page: Page): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBeTruthy()
}

async function ensureTrailVisible(page: Page): Promise<Locator | null> {
  const openDrawer = page.getByRole('button', { name: /Abrir trilha de aulas/ })
  const desktopShortcuts = page.getByRole('navigation', { name: 'Atalhos', exact: true })
  // Após reload, o React pode ainda não ter montado o shell. `isVisible()` não
  // espera e fazia o helper concluir incorretamente que estava no desktop.
  await expect
    .poll(async () => (await openDrawer.isVisible()) || (await desktopShortcuts.isVisible()))
    .toBe(true)
  if (!(await openDrawer.isVisible())) return null
  if ((await openDrawer.getAttribute('aria-expanded')) !== 'true') await openDrawer.click()
  const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
  await expect(dialog).toBeVisible()
  return dialog
}

async function globalLink(page: Page, name: RegExp): Promise<Locator> {
  const dialog = await ensureTrailVisible(page)
  const scope = dialog ?? page.getByRole('navigation', { name: 'Atalhos', exact: true })
  return scope.getByRole('link', { name })
}

async function expectCourseProgress(page: Page, completed: number): Promise<void> {
  const dialog = await ensureTrailVisible(page)
  const scope = dialog ?? page
  await expect(
    scope.getByRole('progressbar', { name: 'Progresso das aulas do curso' }),
  ).toHaveAttribute('aria-valuenow', String(completed))
}

async function tabAte(page: Page, alvo: Locator, limite = 80): Promise<void> {
  await expect(alvo).toBeVisible()
  for (let tentativa = 0; tentativa < limite; tentativa += 1) {
    await page.keyboard.press('Tab')
    if (await alvo.evaluate((element) => element === document.activeElement)) return
  }
  throw new Error(`O foco não alcançou o controle após ${limite} acionamentos de Tab.`)
}

/** Cria a conta e espera a aplicação terminar a transição pós-login.
 *  Navegar antes disso cai de volta na tela de entrada. */
async function criarConta(page: Page, nome: string): Promise<string> {
  const email = emailUnico()
  await page.goto('/')
  await page.getByRole('button', { name: 'Ainda não tenho conta' }).click()
  await page.getByLabel('Nome').fill(nome)
  await page.getByLabel('E-mail').fill(email)
  await page.getByLabel('Senha').fill(SENHA)
  await page.getByRole('button', { name: 'Criar conta' }).click()
  await expect(page).toHaveURL(/\/inicio$/)
  await expect(page.getByRole('heading', { name: 'Hoje' })).toBeVisible()
  return email
}

type PracticeSessionE2E = {
  items: Array<{ exercise: { prompt: string } }>
}

async function iniciarPraticaGuiada(
  page: Page,
  lessonNumber: number,
  courseSlug = LEVEL_1_SLUG,
): Promise<PracticeSessionE2E> {
  const sessaoCriada = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        `/api/courses/${courseSlug}/lessons/${lessonNumber}/practice-sessions` &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  const iniciar = page.getByRole('button', { name: 'Começar Prática guiada' })
  await expect(iniciar).toBeEnabled()
  await iniciar.click()
  const sessao = (await (await sessaoCriada).json()) as PracticeSessionE2E
  await expect(page.locator('.practice-question')).toBeVisible()
  return sessao
}

async function avancarAteEnunciado(
  page: Page,
  sessao: PracticeSessionE2E,
  enunciado: RegExp,
): Promise<Locator> {
  const indice = sessao.items.findIndex((item) => enunciado.test(item.exercise.prompt))
  if (indice < 0) throw new Error(`A sessão não contém o exercício ${enunciado}.`)

  for (let atual = 0; atual < indice; atual += 1) {
    const questao = page.locator('.practice-question')
    await questao.getByRole('button', { name: 'Resposta' }).click()
    await expect(questao.getByText('Resposta', { exact: true })).toBeVisible()
    const proxima = page
      .getByRole('navigation', { name: 'Questões da sessão' })
      .getByRole('button', { name: 'Próxima →' })
    await expect(proxima).toBeEnabled()
    await proxima.click()
    await expect(page.locator('.practice-runner-head')).toContainText(
      `Questão ${atual + 2} de`,
    )
  }

  const questao = page.locator('.practice-question')
  await expect(questao.getByRole('heading', { level: 3 })).toContainText(enunciado)
  return questao
}

test('do cadastro à primeira revisão', async ({ page }) => {
  await test.step('cria a conta', async () => {
    await criarConta(page, 'Jeferson')
  })

  await test.step('o currículo do curso e da unidade vem da API', async () => {
    await page.goto(coursePath(LEVEL_1_SLUG))
    const main = page.locator('#main-content')
    await main.getByRole('link', { name: /Aulas/ }).first().click()
    const lessonLink = main.getByRole('link', { name: /It's Unbelievable/ })
    await expect(lessonLink).toHaveAttribute('href', lessonPath(39))
    await lessonLink.click()
    await expect(page.getByRole('heading', { name: "It's Unbelievable!" })).toBeVisible()
    await expect(main.getByText('Prefixos negativos').first()).toBeVisible()
  })

  await test.step('errar um exercício de vocabulário põe a palavra no deck', async () => {
    await page.goto(practicePath(39))
    const sessao = await iniciarPraticaGuiada(page, 39)
    const exercicio = await avancarAteEnunciado(page, sessao, /honest/i)
    await exercicio.getByRole('textbox').fill('resposta errada')
    await exercicio.getByRole('button', { name: 'Verificar' }).click()
    await expect(exercicio.getByText('Ainda não')).toBeVisible()

    // O contador de revisão aparece na trilha.
    await expect(await globalLink(page, /^Revisar/)).toContainText('1')
  })

  await test.step('revisar a carta e reagendá-la', async () => {
    await (await globalLink(page, /^Revisar/)).click()
    await expect(page.locator('.carta-termo')).toHaveText('dishonest')
    // A tradução não aparece antes de virar.
    await expect(page.locator('.carta-traducao')).toHaveCount(0)

    const showAnswer = page.getByRole('button', { name: 'Mostrar resposta' })
    await showAnswer.focus()
    await page.keyboard.press(' ')
    await expect(page.locator('.carta-traducao')).toHaveText('desonesto')

    await page.keyboard.press('3') // "Bom"
    await expect(page.getByText(/dishonest volta amanhã/)).toBeVisible()
    await expect(
      page.getByRole('heading', { name: 'Nenhum item com estes filtros' }),
    ).toBeVisible()
  })

  await test.step('marcar a aula semeia o vocabulário inteiro', async () => {
    const dialog = await ensureTrailVisible(page)
    const scope = dialog ?? page
    await scope
      .getByRole('button', { name: 'Marcar Level 1 · Aula 39 como estudada' })
      .click()
    await expectCourseProgress(page, 1)
    // 13 itens na aula 39, menos o `dishonest` que já foi revisado hoje.
    await expect(await globalLink(page, /^Revisar/)).toContainText('12')
  })

  await test.step('o progresso sobrevive ao recarregar', async () => {
    await page.reload()
    await expectCourseProgress(page, 1)
    await expect(await globalLink(page, /^Revisar/)).toContainText('12')
  })
})

test('acertar não enche o deck', async ({ page }) => {
  await criarConta(page, 'Certeira')

  await page.goto(practicePath(39))
  await expect(page.getByRole('heading', { name: "It's Unbelievable!" })).toBeVisible()
  const sessao = await iniciarPraticaGuiada(page, 39)
  const exercicio = await avancarAteEnunciado(page, sessao, /honest/i)
  await exercicio.getByRole('textbox').fill('dishonest')
  await exercicio.getByRole('button', { name: 'Verificar' }).click()
  await expect(exercicio.getByText('Correto')).toBeVisible()

  await expect(await globalLink(page, /^Revisar/)).toHaveText('Revisar')
})

test('a jornada guiada retoma e conclui a aula 31', async ({ page }) => {
  await criarConta(page, 'Estudante guiada')

  await page.goto(lessonPath(31))
  await page.getByRole('link', { name: 'Começar estudo' }).click()
  await expect(page.getByText('Etapa 1 de 5')).toBeVisible()

  await page.getByRole('button', { name: /Concluir e ir para Assistir/ }).click()
  await expect(page.getByText('Etapa 2 de 5')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Conversa da Aula 31' })).toBeVisible()

  await page.getByRole('button', { name: 'Mostrar transcrição' }).click()
  const transcript = page.locator('.audio-transcript')
  await expect(transcript.getByText("Don't take the bus. A taxi is faster than a bus.")).toBeVisible()
  await page.getByLabel('Mostrar apoio em português').check()
  await expect(
    transcript.getByText('Não pegue o ônibus. Um táxi é mais rápido que um ônibus.'),
  ).toBeVisible()

  const listening = page.locator('.listening-check')
  const listeningChoice = listening.locator('.ex').filter({ hasText: 'Anna finalmente pega' })
  await listeningChoice.getByRole('radio', { name: 'Metro' }).check()
  await listeningChoice.getByRole('button', { name: 'Verificar' }).click()
  await expect(listeningChoice.getByText('Correto')).toBeVisible()

  // Sem o localStorage, a rota ainda retoma pelo progresso associado à conta.
  // No layout móvel o rótulo visual é oculto para preservar espaço, mas o
  // estado acessível ainda confirma que o servidor terminou de salvar.
  await expect(page.getByText('Progresso sincronizado.')).toHaveText('Progresso sincronizado.')
  await page.evaluate(() => window.localStorage.clear())
  await page.goto(studyPath(31))
  await expect(page.getByText('Etapa 2 de 5')).toBeVisible()

  await page.getByRole('button', { name: /Concluir e ir para Estudar/ }).click()
  await page.getByRole('button', { name: /Concluir e ir para Praticar/ }).click()
  await iniciarPraticaGuiada(page, 31)
  const practice = page.locator('.practice-question')
  await practice.getByRole('button', { name: 'Dica 1' }).click()
  await expect(practice.getByText(/A forma pedida vem antes de/)).toBeVisible()
  await practice.getByRole('textbox').fill('more fast')
  await practice.getByRole('button', { name: 'Verificar' }).click()
  await expect(practice.getByText('Ainda não')).toBeVisible()
  await expect(practice.getByText(/palavra ou estrutura a mais/)).toBeVisible()
  await practice.getByRole('button', { name: 'Dica 2' }).click()
  await expect(practice.getByText(/Acrescente.*-er.*adjetivo curto/)).toBeVisible()
  await expect(practice.getByRole('button', { name: 'Tentar novamente' })).toBeVisible()
  await page.getByRole('button', { name: /Concluir e ir para Revisar/ }).click()
  const writing = page.locator('.writing-workspace')
  const writingText =
    'The Metro is faster than the bus in my city. It is comfortable and usually arrives on time. A visitor should take the Metro to the stadium. The bus is cheaper, but the Metro is my best choice.'
  await writing.getByRole('textbox', { name: 'Seu texto em inglês' }).fill(writingText)
  await expect(writing.getByText('Rascunho salvo.')).toBeVisible()
  await writing.getByRole('button', { name: 'Analisar texto' }).click()
  await expect(
    writing.getByRole('heading', { name: 'Texto pronto para uma nova versão' }),
  ).toBeVisible()
  await expect(writing.getByText('Análise automática por regras locais')).toBeVisible()
  await writing.getByRole('button', { name: 'Criar versão' }).click()
  await expect(writing.getByText('Versão 1 criada.')).toBeVisible()
  const revisedWritingText = `${writingText} It also saves time.`
  const revisedSave = page.waitForResponse(
    (response) =>
      response.url().includes(`/api/writing/prompts/`) &&
      response.request().method() === 'PUT' &&
      response.ok(),
  )
  await writing.getByRole('textbox', { name: 'Seu texto em inglês' }).fill(revisedWritingText)
  await revisedSave
  await expect(writing.getByText('Rascunho salvo.')).toBeVisible()
  await writing.getByRole('button', { name: 'Comparar com texto atual' }).click()
  await expect(writing.getByRole('heading', { name: 'Versão 1 → texto atual' })).toBeVisible()
  await expect(
    writing.locator('.writing-diff-copy').getByText('saves', { exact: true }),
  ).toBeVisible()

  // O rascunho também retorna pelo servidor, mesmo sem o backup do navegador.
  await page.evaluate(() => window.localStorage.clear())
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Seu texto em inglês' })).toHaveValue(revisedWritingText)
  await expect(page.getByRole('heading', { name: 'Versões salvas' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Escute, repita e compare sua voz' })).toBeVisible()
  await expect(page.getByText(/Por padrão, a gravação fica somente nesta tela/)).toBeVisible()
  await page.getByRole('button', { name: 'Concluir aula' }).click()

  await expect(page.getByRole('status')).toContainText('Você percorreu as cinco etapas')
  await expectCourseProgress(page, 1)
})

test('a correção acontece no servidor: o gabarito não viaja antes', async ({ request }) => {
  // Direto no contrato, sem depender de quando o browser dispara a chamada.
  for (const rota of [
    `/api/courses/${LEVEL_1_SLUG}/lessons/31`,
    `/api/courses/${LEVEL_1_SLUG}/lessons/39`,
    '/api/exercises?lesson=31',
  ]) {
    const r = await request.get(rota)
    expect(r.ok()).toBeTruthy()
    const corpo = await r.text()
    expect(corpo).not.toContain('"answers"')
    expect(corpo).toContain('"prompt"')
  }
})

test('metadados editoriais e posição de mídia atravessam a API', async ({ request }) => {
  const register = await request.post('/api/auth/register', {
    data: {
      email: emailUnico(),
      password: SENHA,
      display_name: 'Mídia E2E',
    },
  })
  expect(register.status()).toBe(201)
  const headers = { Authorization: `Bearer ${(await register.json()).access_token as string}` }
  const lesson = await (
    await request.get(`/api/courses/${LEVEL_1_SLUG}/lessons/32`)
  ).json()

  expect(lesson.versions[0]).toMatchObject({
    version: 1,
    status: 'reviewed',
    learning_strategy: 'monitorar',
  })
  expect(lesson.content_sources).toEqual(
    expect.arrayContaining([expect.objectContaining({ kind: 'official', publisher: 'VOA Learning English' })]),
  )
  expect(lesson.media[0].cues).toHaveLength(4)

  const curriculum = await (
    await request.get(`/api/courses/${LEVEL_1_SLUG}/curriculum`)
  ).json()
  const lessonNumbers = curriculum.units.flatMap(
    (unit: { lessons: Array<{ number: number }> }) =>
      unit.lessons.map((currentLesson) => currentLesson.number),
  ) as number[]
  expect(lessonNumbers.length).toBeGreaterThan(0)

  for (const number of lessonNumbers) {
    const current = await (
      await request.get(`/api/courses/${LEVEL_1_SLUG}/lessons/${number}`)
    ).json()
    expect(current.media).toHaveLength(1)
    expect(current.media[0].source_url).toContain('voa-audio.voanews.eu')
    expect(current.media[0].cues.length).toBeGreaterThanOrEqual(4)
    expect(current.exercises.some((exercise: { skill: string }) => exercise.skill === 'listening'))
      .toBeTruthy()
  }

  const mediaId = lesson.media[0].id as number
  expect(await (await request.get(`/api/media/${mediaId}/position`, { headers })).json()).toMatchObject({
    media_id: mediaId,
    position_seconds: 0,
  })
  expect(
    (
      await request.put(`/api/media/${mediaId}/position`, {
        headers,
        data: { position_seconds: 42.5 },
      })
    ).ok(),
  ).toBeTruthy()
  expect(await (await request.get(`/api/media/${mediaId}/position`, { headers })).json()).toMatchObject({
    position_seconds: 42.5,
  })
  expect((await request.delete(`/api/media/${mediaId}/position`, { headers })).status()).toBe(204)
})

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
  await expect(level1Card.getByText('22/52', { exact: true })).toBeVisible()

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
  expect(curriculum.course.published_lessons).toBe(22)
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
      published_lessons: 22,
      viewed_lessons: 0,
      completed_lessons: 0,
      completion_percent: 0,
      status: 'not_started',
    },
    checkpoints: { published: 3, current_completed: 0 },
    certificate: {
      eligible: false,
      required_lessons: 22,
      required_checkpoints: 3,
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
    published_lessons: 22,
    viewed_lessons: 1,
    completed_lessons: 1,
    status: 'in_progress',
  })
  expect(after.certificate).toMatchObject({ eligible: false, automatic_download: false })
  expect(after.incomplete_units).toHaveLength(4)
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
  await expect(metricValue('Conteúdo publicado')).toHaveText('22')
  await expect(metricValue('Aulas vistas')).toHaveText('0 / 22')
  await expect(metricValue('Aulas concluídas')).toHaveText('0 / 22')
  await expect(page.getByRole('progressbar', { name: 'Aulas concluídas no recorte publicado' }))
    .toHaveAttribute('aria-valuenow', '0')

  for (const unit of ['Aulas 31–40', 'Aulas 40–44', 'Aulas 45–49', 'Aulas 50–52']) {
    await expect(page.getByRole('link', { name: new RegExp(unit) })).toBeVisible()
  }
  await expect(
    page.getByRole('heading', { name: 'Certificado do recorte: ainda não elegível' }),
  ).toBeVisible()
  await expect(page.getByText(/Regra deste recorte: 22 aulas e 3 checkpoints/)).toBeVisible()
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

test('gravação oral exige consentimento e pode ser excluída', async ({ request }) => {
  const register = await request.post('/api/auth/register', {
    data: {
      email: emailUnico(),
      password: SENHA,
      display_name: 'Speaking E2E',
    },
  })
  expect(register.status()).toBe(201)
  const token = (await register.json()).access_token as string
  const headers = { Authorization: `Bearer ${token}` }
  const assistStatus = await request.get('/api/assist/status', { headers })
  expect(assistStatus.ok()).toBeTruthy()
  expect(await assistStatus.json()).toMatchObject({
    transcription_enabled: false,
    writing_enabled: false,
    used_today: 0,
  })
  const lesson = await (
    await request.get(`/api/courses/${LEVEL_1_SLUG}/lessons/31`)
  ).json()
  const cueId = lesson.media[0].cues[0].id as number

  const withoutConsent = await request.post('/api/speaking/attempts', {
    headers,
    data: { cue_id: cueId, duration_ms: 1200, consent: false },
  })
  expect(withoutConsent.status()).toBe(422)

  const created = await request.post('/api/speaking/attempts', {
    headers,
    data: { cue_id: cueId, duration_ms: 1200, self_rating: 'almost', consent: true },
  })
  expect(created.status()).toBe(201)
  const attemptId = (await created.json()).id as number
  const uploaded = await request.put(`/api/speaking/attempts/${attemptId}/audio`, {
    headers: { ...headers, 'Content-Type': 'audio/webm' },
    data: 'audio-e2e',
  })
  expect(uploaded.ok()).toBeTruthy()

  const listed = await request.get('/api/speaking/attempts?lesson=31', { headers })
  expect((await listed.json()).map((item: { id: number }) => item.id)).toContain(attemptId)
  expect((await request.get(`/api/speaking/attempts/${attemptId}/audio`, { headers })).ok()).toBeTruthy()

  expect((await request.delete(`/api/speaking/attempts/${attemptId}`, { headers })).status()).toBe(204)
  expect((await request.get(`/api/speaking/attempts/${attemptId}/audio`, { headers })).status()).toBe(404)
})

test('caderno pessoal persiste, edita, exporta e exclui uma anotação', async ({ page }) => {
  await criarConta(page, 'Caderno E2E')
  await (await globalLink(page, /^Caderno$/)).click()
  await expect(page.getByRole('heading', { name: 'Caderno de inglês' })).toBeVisible()
  await expect(page.getByText(/Estas anotações pertencem somente à sua conta/)).toBeVisible()

  const compose = page.locator('.notebook-compose')
  await compose.getByLabel('Tipo').selectOption('favorite_phrase')
  await compose.getByLabel('Conteúdo').fill('A taxi is faster than a bus.')
  await compose.getByRole('button', { name: 'Salvar no caderno' }).click()
  await expect(page.getByText('Anotação salva no seu caderno.')).toBeVisible()
  await expect(page.getByText('A taxi is faster than a bus.')).toBeVisible()

  await page.reload()
  await expect(page.getByText('A taxi is faster than a bus.')).toBeVisible()
  await page.getByRole('button', { name: 'Editar' }).click()
  await page.getByLabel('Conteúdo da anotação').fill('The subway is faster than my car.')
  await page.getByRole('button', { name: 'Salvar alteração' }).click()
  await expect(page.getByText('The subway is faster than my car.')).toBeVisible()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Exportar meus dados' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('aulas-ingles-dados.json')

  await page.getByRole('button', { name: 'Excluir' }).click()
  await expect(page.getByText('Nenhuma anotação com estes filtros.')).toBeVisible()
})

test('painel Hoje orienta, salva o plano e só calcula competência com amostra', async ({ page }) => {
  await criarConta(page, 'Painel E2E')

  await expect(page.getByRole('heading', { name: 'Hoje' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Começar a Aula 31' })).toBeVisible()
  await expect(page.getByText(/próxima aula ainda não concluída/)).toBeVisible()
  const grammarBefore = page.locator('.today-skills li').filter({ hasText: 'Gramática' })
  await expect(grammarBefore.getByText('Dados insuficientes (0/3)')).toBeVisible()

  await page.getByRole('textbox', { name: 'Meta', exact: true }).fill('Inglês para uma viagem')
  await page.getByLabel('Minutos por semana').fill('120')
  await page.getByText('Qua', { exact: true }).click()
  await page.getByText('Sáb', { exact: true }).click()
  await page.getByRole('button', { name: 'Salvar plano' }).click()
  await expect(page.getByRole('status')).toHaveText('Plano salvo.')
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Meta', exact: true })).toHaveValue(
    'Inglês para uma viagem',
  )
  await expect(page.getByLabel('Minutos por semana')).toHaveValue('120')

  await page.goto(practicePath(31))
  await iniciarPraticaGuiada(page, 31)
  const exercise = page.locator('.practice-question')
  for (const answer of ['more fast', 'fastest', 'faster']) {
    await exercise.getByRole('textbox').fill(answer)
    await exercise.getByRole('button', { name: 'Verificar' }).click()
    if (answer !== 'faster') {
      await expect(exercise.getByText('Ainda não')).toBeVisible()
      await exercise.getByRole('button', { name: 'Tentar novamente' }).click()
    } else {
      await expect(exercise.getByText('Correto')).toBeVisible()
    }
  }

  await page.goto('/')
  const grammarAfter = page.locator('.today-skills li').filter({ hasText: 'Gramática' })
  await expect(grammarAfter.getByText('33%')).toBeVisible()
  await expect(grammarAfter.getByText(/Tópico para reforçar/)).toBeVisible()
})

test('revisão multimodal filtra e permite suspender, reativar e excluir', async ({ page }) => {
  await criarConta(page, 'Revisão multimodal E2E')
  await page.goto(practicePath(31))

  await iniciarPraticaGuiada(page, 31)
  const exercise = page.locator('.practice-question')
  await exercise.getByRole('textbox').fill('more fast')
  await exercise.getByRole('button', { name: 'Verificar' }).click()
  await expect(exercise.getByText('Ainda não')).toBeVisible()

  await (await globalLink(page, /^Revisar/)).click()
  await expect(page.getByRole('heading', { name: 'Revisar' })).toBeVisible()
  await expect(page.getByText('Por que voltou?')).toBeVisible()
  await expect(page.getByText(/resposta incorreta/)).toBeVisible()
  await page.getByLabel('Tipo').selectOption('grammar_error')
  await page.getByLabel('Competência').selectOption('grammar')
  await page.getByLabel('Duração').selectOption('2')
  await expect(page.locator('.review-card-meta')).toContainText('Erro gramatical')

  await page.getByRole('button', { name: 'Suspender item' }).click()
  await expect(page.getByRole('status')).toContainText('Item suspenso')
  await expect(page.getByRole('heading', { name: 'Nenhum item com estes filtros' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Itens suspensos' })).toBeVisible()

  await page.getByRole('button', { name: 'Reativar' }).click()
  await expect(page.getByRole('button', { name: 'Suspender item' })).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Excluir item' }).click()
  await expect(page.getByRole('status')).toContainText('Item excluído')
  await expect(page.getByRole('heading', { name: 'Nenhum item com estes filtros' })).toBeVisible()
})

test('PWA mantém a aula pública disponível offline', async ({ page, context }) => {
  await criarConta(page, 'Offline E2E')
  await page.goto(lessonPath(31))
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()

  // Aguarda o worker assumir a página e recarrega online para colocar a aula
  // pública e o bundle versionado no cache da instalação.
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((resolve) =>
        navigator.serviceWorker.addEventListener('controllerchange', () => resolve(), { once: true }),
      )
    }
  })
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()

  await context.setOffline(true)
  try {
    await page.reload()
    await expect(page.getByText(/Você está offline/)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Abrir laboratório' })).toHaveAttribute(
      'href',
      practicePath(31),
    )
  } finally {
    await context.setOffline(false)
  }
})

test.describe('laboratório de exercícios por aula', () => {
  test('abre o pack autoral da Aula 31 pela página da aula', async ({ page }) => {
    await criarConta(page, 'Laboratório Aula 31')
    await page.goto(lessonPath(31))

    const abrirLaboratorio = page.getByRole('link', { name: 'Abrir laboratório' })
    await expect(abrirLaboratorio).toHaveAttribute('href', practicePath(31))
    await abrirLaboratorio.click()

    await expect(page).toHaveURL(new RegExp(`${practicePath(31)}$`))
    await expect(
      page.getByRole('heading', { level: 1, name: 'Take Me Out to the Ball Game' }),
    ).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Escolha como praticar' })).toBeVisible()
    await expect(
      page.getByRole('status').filter({ hasText: 'atividades disponíveis neste recorte' }),
    ).toHaveText('10 de 10 atividades disponíveis neste recorte.')
  })

  test('corrige com dica e retoma a sessão guiada na questão salva', async ({ page }) => {
    await criarConta(page, 'Prática guiada E2E')
    await page.goto(practicePath(31))
    await page.getByRole('button', { name: 'Começar Prática guiada' }).click()

    const questao = page.locator('.practice-question')
    const resposta = questao.getByRole('textbox', { name: 'Resposta do exercício 1' })
    await resposta.fill('more fast')
    await questao.getByRole('button', { name: 'Verificar' }).click()
    await expect(questao.getByText('Ainda não', { exact: true })).toBeVisible()

    await questao.getByRole('button', { name: 'Dica 1' }).click()
    await expect(questao.getByRole('list', { name: 'Dicas abertas' })).toContainText('Dica 1')
    await questao.getByRole('button', { name: 'Tentar novamente' }).click()
    await expect(resposta).toBeFocused()
    await resposta.fill('faster')
    await questao.getByRole('button', { name: 'Verificar' }).click()
    await expect(questao.getByText('Correto', { exact: true })).toBeVisible()
    await expect(
      page.getByRole('progressbar', { name: 'Progresso da sessão de exercícios' }),
    ).toHaveAttribute('aria-valuenow', '1')

    const proxima = page
      .getByRole('navigation', { name: 'Questões da sessão' })
      .getByRole('button', { name: 'Próxima →' })
    await expect(proxima).toBeEnabled()
    const posicaoSalva = page.waitForResponse(
      (response) =>
        /\/api\/practice-sessions\/\d+\/position$/.test(new URL(response.url()).pathname) &&
        response.request().method() === 'PUT' &&
        response.ok(),
    )
    await proxima.click()
    await posicaoSalva
    await expect(page.getByRole('textbox', { name: 'Resposta do exercício 2' })).toBeVisible()

    await page.reload()
    await expect(page.getByRole('heading', { name: 'Continue de onde parou' })).toBeVisible()
    await page.getByRole('button', { name: 'Retomar sessão' }).click()
    await expect(page.getByRole('textbox', { name: 'Resposta do exercício 2' })).toBeVisible()
    await expect(page.locator('.practice-question').getByRole('heading', { level: 3 })).toBeFocused()
  })

  test('revelar respostas conclui itens sem contar domínio na primeira tentativa', async ({
    page,
  }) => {
    await criarConta(page, 'Resposta revelada E2E')
    await page.goto(practicePath(31))
    await page.getByLabel('Objetivo').selectOption('correct')
    await expect(
      page.getByRole('status').filter({ hasText: 'atividades disponíveis neste recorte' }),
    ).toHaveText('2 de 10 atividades disponíveis neste recorte.')
    await page.getByRole('button', { name: 'Começar Prática guiada' }).click()

    let questao = page.locator('.practice-question')
    await questao.getByRole('button', { name: 'Resposta' }).click()
    await expect(questao.getByText('Resposta', { exact: true })).toBeVisible()

    const proxima = page
      .getByRole('navigation', { name: 'Questões da sessão' })
      .getByRole('button', { name: 'Próxima →' })
    await expect(proxima).toBeEnabled()
    await proxima.click()
    await expect(page.getByRole('textbox', { name: 'Resposta do exercício 2' })).toBeVisible()

    questao = page.locator('.practice-question')
    await questao.getByRole('button', { name: 'Resposta' }).click()
    await page
      .getByRole('navigation', { name: 'Questões da sessão' })
      .getByRole('button', { name: 'Ver resumo' })
      .click()
    const resumo = page.getByRole('region', { name: 'Resumo da sua prática' })
    await expect(resumo).toBeVisible()
    const primeiraTentativa = resumo.locator('dt').filter({ hasText: /^Primeira tentativa$/ })
    const respostasReveladas = resumo.locator('dt').filter({ hasText: /^Respostas reveladas$/ })
    await expect(primeiraTentativa.locator('..').locator('dd')).toHaveText('0')
    await expect(respostasReveladas.locator('..').locator('dd')).toHaveText('2')
    await expect(resumo).toContainText(
      'Respostas reveladas ajudam a aprender, mas não são contadas como domínio na primeira tentativa.',
    )
  })

  test('avança pelo teclado e move o foco para o enunciado seguinte', async ({ page }) => {
    await criarConta(page, 'Teclado do laboratório E2E')
    await page.goto(practicePath(31))
    await page.getByLabel('Objetivo').selectOption('correct')
    await page.getByRole('button', { name: 'Começar Prática guiada' }).click()

    const resposta = page.getByRole('textbox', { name: 'Resposta do exercício 1' })
    await tabAte(page, resposta)
    await page.keyboard.type('faster')
    await page.keyboard.press('Enter')
    await expect(page.locator('.practice-question').getByText('Correto', { exact: true })).toBeVisible()

    const proxima = page
      .getByRole('navigation', { name: 'Questões da sessão' })
      .getByRole('button', { name: 'Próxima →' })
    await expect(proxima).toBeEnabled()
    await tabAte(page, proxima)
    await page.keyboard.press('Enter')

    await expect(page.getByRole('textbox', { name: 'Resposta do exercício 2' })).toBeVisible()
    await expect(page.locator('.practice-question').getByRole('heading', { level: 3 })).toBeFocused()
  })

  test('packs das Aulas 38 e 40 carregam e aplicam filtros combináveis', async ({ page }) => {
    await criarConta(page, 'Packs 38 e 40 E2E')

    for (const pack of [
      { number: 38, title: "She's My Best Friend!", total: 11, recognize: 1 },
      { number: 40, title: 'The Woods Are Alive', total: 12, recognize: 4 },
    ]) {
      await page.goto(practicePath(pack.number))
      await expect(page.getByRole('heading', { level: 1, name: pack.title })).toBeVisible()
      const contador = page
        .getByRole('status')
        .filter({ hasText: 'atividades disponíveis neste recorte' })
      await expect(contador).toHaveText(
        `${pack.total} de ${pack.total} atividades disponíveis neste recorte.`,
      )

      await page.getByLabel('Competência').selectOption('listening')
      await expect(contador).toHaveText(`3 de ${pack.total} atividades disponíveis neste recorte.`)
      await page.getByLabel('Objetivo').selectOption('listen')
      await expect(contador).toHaveText(`3 de ${pack.total} atividades disponíveis neste recorte.`)

      await page.getByLabel('Competência').selectOption('')
      await page.getByLabel('Objetivo').selectOption('recognize')
      await expect(contador).toHaveText(
        `${pack.recognize} de ${pack.total} atividades disponíveis neste recorte.`,
      )
    }
  })

  test('tentativa offline preserva idempotência e contexto da sessão ao sincronizar', async ({
    page,
    context,
  }) => {
    await criarConta(page, 'Fila da prática E2E')
    await page.goto(practicePath(31))
    await page.getByRole('radio', { name: /Desafio rápido/ }).check()

    const sessaoCriada = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/courses/voa-level-1/lessons/31/practice-sessions') &&
        response.request().method() === 'POST' &&
        response.ok(),
    )
    await page.getByRole('button', { name: 'Começar Desafio rápido' }).click()
    const sessao = (await (await sessaoCriada).json()) as {
      id: number
      items: Array<{ exercise: { id: number } }>
    }
    await expect(
      page.getByRole('progressbar', { name: 'Progresso da sessão de exercícios' }),
    ).toBeVisible()

    let offline = true
    await context.setOffline(true)
    try {
      await expect.poll(() => page.evaluate(() => navigator.onLine)).toBe(false)
      await expect(page.getByRole('status').filter({ hasText: 'Você está offline' })).toBeVisible()
      const questao = page.locator('.practice-question')
      await questao.getByRole('textbox', { name: 'Resposta do exercício 1' }).fill('faster')
      await questao.getByRole('button', { name: 'Verificar' }).click()
      await expect(questao.getByText('Na fila', { exact: true })).toBeVisible()

      const armazenamento = (await page.evaluate(() => {
        const raw = localStorage.getItem('aulas:offline-attempts:v2')
        return raw ? JSON.parse(raw) : null
      })) as {
        version: number
        attempts: Array<{
          userId: number
          exerciseId: number
          answer: string
          idempotencyKey: string
          sessionId?: number
          courseSlug?: string
          lessonNumber?: number
        }>
      } | null
      expect(armazenamento).not.toBeNull()
      expect(armazenamento?.version).toBe(2)
      expect(armazenamento?.attempts).toHaveLength(1)
      const tentativa = armazenamento!.attempts[0]!
      expect(tentativa.userId).toBeGreaterThan(0)
      expect(tentativa.exerciseId).toBe(sessao.items[0]?.exercise.id)
      expect(tentativa.answer).toBe('faster')
      expect(tentativa.idempotencyKey).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
      )
      expect(tentativa.sessionId).toBe(sessao.id)
      expect(tentativa.courseSlug).toBe(LEVEL_1_SLUG)
      expect(tentativa.lessonNumber).toBe(31)

      const sincronizacao = page.waitForRequest(
        (request) =>
          /\/api\/exercises\/\d+\/attempt$/.test(new URL(request.url()).pathname) &&
          request.method() === 'POST',
      )
      await context.setOffline(false)
      offline = false
      const requisicao = await sincronizacao
      expect(requisicao.postDataJSON()).toMatchObject({
        answer: 'faster',
        idempotency_key: tentativa.idempotencyKey,
        practice_session_id: sessao.id,
      })
      await expect(page.getByText('1 tentativa foi sincronizada.')).toBeVisible()
      await expect
        .poll(() =>
          page.evaluate(() => {
            const raw = localStorage.getItem('aulas:offline-attempts:v2')
            if (!raw) return 0
            const parsed = JSON.parse(raw) as { attempts?: unknown[] }
            return parsed.attempts?.length ?? 0
          }),
        )
        .toBe(0)
    } finally {
      if (offline) await context.setOffline(false)
    }
  })
})

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

test('Sprint 26 permanece publicada após a expansão da Sprint 27', async ({
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
    published_lessons: 15,
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
  expect(curriculum.units.slice(3).every((unit) => (
    unit.status === 'planned' && unit.published_lessons === 0 && unit.lessons.length === 0
  ))).toBeTruthy()
  expect(curriculum.units.at(-1)?.review).toBeNull()

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
  await expect(level2Card.getByText('15/30', { exact: true })).toBeVisible()
  await expect(level2Card.getByText('Publicado', { exact: true })).toBeVisible()

  await level2Card.getByRole('link', { name: 'Ver unidades' }).click()
  await expect(page).toHaveURL(new RegExp(`${coursePath(LEVEL_2_SLUG)}$`))
  await expect(page.getByRole('heading', { name: 'Mapa do curso' })).toBeVisible()
  await expect(page.getByText(/Level 2 · Intermediário · VOA Learning English/)).toBeVisible()
  const unitCards = page.locator('.unit-card-grid')
  await expect(unitCards.locator('a')).toHaveCount(3)
  await expect(unitCards.getByText('Em preparação', { exact: true })).toHaveCount(3)
  await expect(unitCards.locator('a', { hasText: 'Aulas 26–30' })).toHaveCount(0)

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
  await expect(page.getByRole('link', { name: 'Ver progresso do curso' })).toHaveAttribute(
    'href',
    courseCompletionPath(LEVEL_2_SLUG),
  )
  await expect(page.getByRole('link', { name: /Continuar em Level 2 · Aula 16/ })).toHaveCount(0)

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
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: 'Trilha de estudo' })).toHaveCount(0)
  }
  await expect(
    page.getByRole('heading', { name: 'Level 1 · Começar a Aula 31' }),
  ).toBeVisible()
  await expect(page.getByText(/Level 2 · Aula 1/)).toHaveCount(0)
})

test('Sprint 25 mantém o piloto Level 2 utilizável em mobile e zoom equivalente a 200%', async ({
  page,
}) => {
  await page.setViewportSize({ width: 640, height: 360 })
  await criarConta(page, 'Reflow Level 2 Sprint 25')
  await page.goto(lessonPath(1, LEVEL_2_SLUG))

  await expect(page.getByRole('heading', { level: 1, name: 'Budget Cuts' })).toBeVisible()
  await expectNoHorizontalScroll(page)
  const openTrail = page.getByRole('button', { name: /Abrir trilha de aulas/ })
  await expect(openTrail).toContainText('Level 2 · Aula 1 · Budget Cuts')
  await tabAte(page, openTrail)
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('combobox', { name: 'Curso' })).toHaveValue(LEVEL_2_SLUG)
  await expect(
    dialog.getByRole('heading', { name: "Let's Learn English — Level 2" }),
  ).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(openTrail).toBeFocused()

  const accessibility = await new AxeBuilder({ page })
    .include('#main-content')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(accessibility.violations).toEqual([])
})

test('rota canônica mantém aula ativa e navegação completa por teclado', async ({ page }) => {
  await criarConta(page, 'Navegação E2E')
  await page.goto(lessonPath(31))

  await expect(page).toHaveURL(new RegExp(`${lessonPath(31)}$`))
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
  const dialog = await ensureTrailVisible(page)
  const navigation = dialog ?? page.getByRole('complementary', { name: 'Navegação do curso' })
  const activeLesson = navigation.getByRole('link', {
    name: /31.*Take Me Out to the Ball Game/,
  })
  await expect(activeLesson).toHaveAttribute('aria-current', 'page')

  const shortcuts = navigation.getByRole('navigation', { name: 'Atalhos' })
  for (const name of ['Hoje', 'Cursos', 'Revisar', 'Caderno', 'Avaliação']) {
    await expect(shortcuts.getByRole('link', { name: new RegExp(`^${name}`) })).toBeVisible()
  }
  expect(
    await shortcuts.evaluate(
      (navigation) => {
        const unitButton = navigation
          .closest('.trail-panel')
          ?.querySelector('button[aria-controls*="-trail-unit-"]')
        return (
          unitButton !== null &&
          Boolean(
            navigation.compareDocumentPosition(unitButton) & Node.DOCUMENT_POSITION_FOLLOWING,
          )
        )
      },
    ),
  ).toBeTruthy()

  const courseSelector = navigation.getByRole('combobox', { name: 'Curso' })
  await courseSelector.focus()
  for (const name of ['Hoje', 'Cursos', 'Revisar', 'Caderno', 'Avaliação', 'Mapa da unidade']) {
    await page.keyboard.press('Tab')
    await expect(shortcuts.getByRole('link', { name: new RegExp(`^${name}`) })).toBeFocused()
  }
  await page.keyboard.press('Tab')
  const search = navigation.getByRole('searchbox', { name: 'Buscar aula' })
  await expect(search).toBeFocused()
  await page.keyboard.type('The Woods Are Alive')
  const lesson40 = navigation.getByRole('link', { name: /40.*The Woods Are Alive/ })
  await tabAte(page, lesson40, 10)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`${lessonPath(40)}$`))
  await expect(page.getByRole('heading', { name: 'The Woods Are Alive' })).toBeVisible()
})

test('drawer da trilha preserva foco e reflow nos viewports críticos', async ({ page }) => {
  await criarConta(page, 'Drawer E2E')
  const viewports = [
    { name: '320 px', width: 320, height: 640 },
    { name: '360 px', width: 360, height: 740 },
    { name: '768 px', width: 768, height: 1024 },
    { name: 'zoom equivalente a 200%', width: 640, height: 360 },
  ]

  for (const viewport of viewports) {
    await test.step(viewport.name, async () => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(lessonPath(31))
      await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
      await expectNoHorizontalScroll(page)

      const openDrawer = page.getByRole('button', { name: /Abrir trilha de aulas/ })
      await expect(openDrawer).toHaveAttribute('aria-expanded', 'false')
      await openDrawer.focus()
      await page.keyboard.press('Enter')

      const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
      await expect(dialog).toBeVisible()
      await expect(openDrawer).toHaveAttribute('aria-expanded', 'true')
      await expect(dialog.getByRole('searchbox', { name: 'Buscar aula' })).toBeFocused()
      await expectNoHorizontalScroll(page)

      for (let index = 0; index < 24; index += 1) {
        await page.keyboard.press('Tab')
        expect(
          await dialog.evaluate((element) => element.contains(document.activeElement)),
        ).toBeTruthy()
      }

      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(openDrawer).toHaveAttribute('aria-expanded', 'false')
      await expect(openDrawer).toBeFocused()
      await expectNoHorizontalScroll(page)
    })
  }
})

test('cadastro permanece acessível em viewport equivalente a zoom de 200%', async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 360 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Ainda não tenho conta' }).click()

  const caixa = page.locator('.login-caixa')
  const nome = page.getByLabel('Nome')
  await expect(caixa).toBeVisible()
  await expect(nome).toBeVisible()
  await expect(nome).toBeFocused()

  expect(await nome.evaluate((element) => element.getBoundingClientRect().height)).toBeLessThan(60)
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
  expect(await caixa.evaluate((element) => element.getBoundingClientRect().top)).toBeGreaterThanOrEqual(0)
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
  ).toBeTruthy()
})

test('cadastro e salto ao conteúdo funcionam com teclado real do navegador', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByLabel('E-mail')).toBeVisible()

  await page.keyboard.press('Tab')
  await expect(page.getByLabel('E-mail')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('Senha')).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByLabel('E-mail')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByLabel('E-mail')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('Senha')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Ainda não tenho conta' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Nome')).toBeFocused()

  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Já tenho conta' })).toBeFocused()
  await page.keyboard.press('Space')
  await expect(page.getByRole('button', { name: 'Ainda não tenho conta' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Nome')).toBeFocused()

  await page.keyboard.type('Teclado E2E')
  await page.keyboard.press('Tab')
  await page.keyboard.type(emailUnico())
  await page.keyboard.press('Tab')
  await page.keyboard.type(SENHA)
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Criar conta' })).toBeFocused()
  await page.keyboard.press('Enter')

  await expect(page).toHaveURL(/\/inicio$/)
  await expect(page.getByRole('heading', { name: 'Hoje' })).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Pular para o conteúdo' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()

  await page.goto(lessonPath(31))
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()

  const comecar = page.getByRole('link', { name: 'Começar estudo' })
  await tabAte(page, comecar)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`${studyPath(31, 'preparar')}$`))

  const avancar = page.getByRole('button', { name: 'Concluir e ir para Assistir' })
  await tabAte(page, avancar)
  await page.keyboard.press('Space')
  await expect(page).toHaveURL(new RegExp(`${studyPath(31, 'assistir')}$`))
  await expect(page.getByRole('heading', { name: 'Escute primeiro pelo contexto' })).toBeVisible()

  await page.goto(practicePath(31))
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
  const iniciarPratica = page.getByRole('button', { name: 'Começar Prática guiada' })
  await tabAte(page, iniciarPratica)
  await page.keyboard.press('Enter')
  await expect(page.locator('.practice-question')).toBeVisible()
  const resposta = page.getByLabel('Resposta do exercício 1')
  await tabAte(page, resposta)
  await page.keyboard.type('faster')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Verificar' }).first()).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByText('Correto').first()).toBeVisible()

  const compactOpen = page.getByRole('button', { name: /Abrir trilha de aulas/ })
  let caderno: Locator
  if (await compactOpen.isVisible()) {
    await tabAte(page, compactOpen)
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
    await expect(dialog).toBeVisible()
    caderno = dialog.getByRole('link', { name: 'Caderno' })
  } else {
    caderno = page.getByRole('link', { name: 'Caderno' })
  }
  await tabAte(page, caderno)
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Caderno de inglês' })).toBeVisible()

  const anotacao = page.getByLabel('Conteúdo')
  await tabAte(page, anotacao)
  await page.keyboard.type('Comparatives use than.')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Salvar no caderno' })).toBeFocused()
  await page.keyboard.press('Space')
  await expect(page.getByRole('status')).toHaveText('Anotação salva no seu caderno.')

  let revisar: Locator
  if (await compactOpen.isVisible()) {
    await tabAte(page, compactOpen)
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
    await expect(dialog).toBeVisible()
    revisar = dialog.getByRole('link', { name: /^Revisar/ })
  } else {
    revisar = page.getByRole('link', { name: /^Revisar/ })
  }
  await tabAte(page, revisar)
  await page.keyboard.press('Enter')
  await expect(
    page.getByRole('heading', { name: /Revisar|Nada para revisar agora|Nenhum item/ }),
  ).toBeVisible()

  const tipo = page.getByLabel('Tipo')
  await tabAte(page, tipo)
  await page.keyboard.press('v')
  await expect(tipo).toHaveValue('vocabulary')
})

test('login e cadastro preservam controles em contraste forçado', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' })
  await page.goto('/')

  expect(await page.evaluate(() => matchMedia('(forced-colors: active)').matches)).toBeTruthy()
  await expect(page.getByLabel('E-mail')).toBeVisible()
  await expect(page.getByLabel('Senha')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()

  await page.keyboard.press('Tab')
  await expect(page.getByLabel('E-mail')).toBeFocused()
  expect(
    await page.getByLabel('E-mail').evaluate((element) => getComputedStyle(element).outlineStyle),
  ).not.toBe('none')

  await page.getByRole('button', { name: 'Ainda não tenho conta' }).click()
  await expect(page.getByLabel('Nome')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Criar conta' })).toBeVisible()

  const resultado = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(
    resultado.violations.filter(
      ({ impact }) => impact === 'serious' || impact === 'critical',
    ),
  ).toEqual([])

  await criarConta(page, 'Contraste E2E')
  for (const rota of [
    '/',
    lessonPath(31),
    studyPath(40, 'assistir'),
    '/revisar',
    '/caderno',
  ]) {
    await page.goto(rota)
    await expect(page.locator('#main-content')).toBeVisible()
    const pagina = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze()
    expect(
      pagina.violations.filter(
        ({ impact }) => impact === 'serious' || impact === 'critical',
      ),
    ).toEqual([])
  }
})

test('painel e aula não têm violações WCAG sérias ou críticas', async ({ page }) => {
  await criarConta(page, 'Acessibilidade E2E')

  const painel = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(painel.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical'))
    .toEqual([])

  await page.goto(lessonPath(40))
  await expect(page.getByRole('heading', { name: 'The Woods Are Alive' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Começar estudo' })).toHaveAttribute(
    'href',
    studyPath(40),
  )
  await page.goto(studyPath(40, 'assistir'))
  await expect(page.getByRole('heading', { name: 'Conversa da Aula 40' })).toBeVisible()
  await expect(page.getByText('What part does the director give Anna?')).toBeVisible()
  const aula = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(aula.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical'))
    .toEqual([])
})
