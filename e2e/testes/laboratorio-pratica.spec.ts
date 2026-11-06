import { expect, test } from '@playwright/test'

import {
  LEVEL_1_SLUG,
  lessonPath,
  practicePath,
  readAttemptQueue,
  tabAte,
  criarConta,
} from '../journey-helpers'

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

  test('duas abas sincronizam a fila com API real e retry idempotente', async ({ page, context }) => {
    await criarConta(page, 'Duas abas Sprint 37')
    const other = await context.newPage()
    const tabs = [page, other]
    const lessons = [31, 32]
    const sessions: number[] = []
    // Carrega autenticação sequencialmente; concorrência de refresh é escopo BE-38.
    for (const [index, tab] of tabs.entries()) {
      const lesson = lessons[index]!
      await tab.goto(practicePath(lesson))
      await tab.getByRole('radio', { name: /Desafio rápido/ }).check()
      const created = tab.waitForResponse((response) =>
        response.url().endsWith('/api/courses/voa-level-1/lessons/' + lesson + '/practice-sessions')
        && response.request().method() === 'POST' && response.ok())
      await tab.getByRole('button', { name: 'Começar Desafio rápido' }).click()
      sessions.push((await (await created).json()).id)
      await expect(tab.locator('.practice-question').getByRole('textbox')).toBeVisible()
    }
    const results: Array<{ id: number; sessionId: number; token: string }> = []
    for (const tab of tabs) {
      tab.on('response', async (response) => {
        if (/\/api\/exercises\/\d+\/attempt$/.test(new URL(response.url()).pathname)
          && response.request().method() === 'POST' && response.ok()) {
          const data = await response.json()
          results.push({
            id: data.attempt_id, sessionId: data.session.session_id,
            token: (await response.request().headerValue('authorization'))!,
          })
        }
      })
    }
    await context.setOffline(true)
    try {
      await Promise.all(tabs.map(async (tab, index) => {
        await expect.poll(() => tab.evaluate(() => navigator.onLine)).toBe(false)
        const question = tab.locator('.practice-question')
        await question.getByRole('textbox', { name: 'Resposta do exercício 1' }).fill(index === 0 ? 'faster' : 'questions')
        await question.getByRole('button', { name: 'Verificar' }).click()
        await expect(question.getByText('Na fila', { exact: true })).toBeVisible()
      }))
      const queued = (await readAttemptQueue(page)).attempts
      expect(queued).toHaveLength(2)
      expect(new Set(queued.map((item) => item.idempotencyKey)).size).toBe(2)
      expect(queued.map((item) => item.sessionId).sort()).toEqual(sessions.sort())
      await context.setOffline(false)
      await expect.poll(async () => (await readAttemptQueue(page)).attempts.length).toBe(0)
      await expect.poll(() => results.length).toBe(2)
      expect((await readAttemptQueue(other)).receipts).toHaveLength(2)
      for (const attempt of queued) {
        const first = results.find((item) => item.sessionId === attempt.sessionId)!
        const retry = await page.request.post('/api/exercises/' + attempt.exerciseId + '/attempt', {
          headers: { Authorization: first.token },
          data: {
            answer: attempt.answer, idempotency_key: attempt.idempotencyKey,
            practice_session_id: attempt.sessionId,
          },
        })
        expect(retry.status()).toBe(200)
        expect(await retry.json()).toMatchObject({
          attempt_id: first.id, session: { session_id: attempt.sessionId, attempt_count: 1 },
        })
      }
    } finally {
      await context.setOffline(false)
      await other.close()
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

      const armazenamento = await readAttemptQueue(page)
      expect(armazenamento.version).toBe(1) // schema IDB, não a antiga versão localStorage
      expect(armazenamento.attempts).toHaveLength(1)
      expect(armazenamento.receipts).toHaveLength(0)
      const tentativa = armazenamento.attempts[0]!
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
      // Request.clone() pode enviar um stream cujo corpo não é exposto pelo CDP.
      // Verifica persistência/idempotência na API real, não um corpo simulado.
      const resposta = await requisicao.response()
      expect(resposta?.status()).toBe(200)
      const primeiroResultado = await resposta!.json()
      expect(primeiroResultado).toMatchObject({
        correct: true, session: { session_id: sessao.id, attempt_count: 1 },
      })
      const authorization = await requisicao.headerValue('authorization')
      expect(authorization).toBeTruthy()
      const repeticao = await page.request.post(`/api/exercises/${tentativa.exerciseId}/attempt`, {
        headers: { Authorization: authorization! },
        data: {
          answer: 'faster',
          idempotency_key: tentativa.idempotencyKey,
          practice_session_id: sessao.id,
        },
      })
      expect(repeticao.status()).toBe(200)
      expect(await repeticao.json()).toMatchObject({
        attempt_id: primeiroResultado.attempt_id,
        correct: true, session: { session_id: sessao.id, attempt_count: 1 },
      })
      await expect(page.getByRole('complementary', { name: 'Fila de respostas' })
        .getByRole('status')).toContainText('1 tentativa(s) sincronizada(s).')
      await expect.poll(async () => (await readAttemptQueue(page)).attempts.length).toBe(0)
      const expectedReceipt = { userId: tentativa.userId, idempotencyKey: tentativa.idempotencyKey }
      expect((await readAttemptQueue(page)).receipts).toEqual([expectedReceipt])
      await page.reload()
      await expect(page.getByRole('heading', { level: 1, name: 'Take Me Out to the Ball Game' })).toBeVisible()
      const reaberta = await readAttemptQueue(page)
      expect(reaberta.attempts).toHaveLength(0)
      expect(reaberta.receipts).toEqual([expectedReceipt])
    } finally {
      if (offline) await context.setOffline(false)
    }
  })
})
