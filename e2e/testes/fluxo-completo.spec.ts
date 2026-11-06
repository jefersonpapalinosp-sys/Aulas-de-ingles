import { expect, test } from '@playwright/test'

import { randomUUID } from 'node:crypto'

import {
  emailUnico,
  SENHA,
  LEVEL_1_SLUG,
  coursePath,
  lessonPath,
  practicePath,
  studyPath,
  ensureTrailVisible,
  globalLink,
  expectCourseProgress,
  criarConta,
  iniciarPraticaGuiada,
  avancarAteEnunciado,
} from '../journey-helpers'

test('frontend aplica headers de segurança sem bloquear o localhost HTTP', async ({ request }) => {
  const response = await request.get('/')
  expect(response.ok()).toBeTruthy()
  const headers = response.headers()
  expect(headers['content-security-policy']).toContain("default-src 'self'")
  expect(headers['content-security-policy']).toContain('https://voa-audio.voanews.eu')
  expect(headers['content-security-policy']).not.toContain('upgrade-insecure-requests')
  expect(headers['x-frame-options']).toBe('DENY')
  expect(headers['x-content-type-options']).toBe('nosniff')
  expect(headers['referrer-policy']).toBe('no-referrer')
  expect(headers['permissions-policy']).toContain('microphone=(self)')
})

test('do cadastro à primeira revisão', async ({ page }) => {
  await test.step('cria a conta', async () => {
    await criarConta(page, 'Jeferson')
  })

  await test.step('o currículo do curso e da unidade vem da API', async () => {
    await page.goto(coursePath(LEVEL_1_SLUG))
    const main = page.locator('#main-content')
    // Desde a Sprint 31 o bloco 1–5 abre o curso, então a unidade é escolhida
    // pelo nome em vez da posição.
    await main.getByRole('link', { name: /Aulas 31–40/ }).click()
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
    writing.getByRole('heading', { name: 'Critérios automáticos atendidos' }),
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

  await expect(page.getByRole('status').filter({ hasText: 'Você percorreu as cinco etapas' }))
    .toContainText('Você percorreu as cinco etapas')
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
        data: { position_seconds: 42.5, expected_revision: 0, operation_key: randomUUID(), changed_at: new Date().toISOString() },
      })
    ).ok(),
  ).toBeTruthy()
  expect(await (await request.get(`/api/media/${mediaId}/position`, { headers })).json()).toMatchObject({
    position_seconds: 42.5,
  })
  expect((await request.delete(`/api/media/${mediaId}/position`, {
    headers, params: { expected_revision: 1, operation_key: randomUUID(), changed_at: new Date().toISOString() },
  })).status()).toBe(204)
})
