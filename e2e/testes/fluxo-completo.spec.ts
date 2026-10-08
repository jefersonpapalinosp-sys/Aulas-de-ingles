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

import type { Page } from '@playwright/test'

function emailUnico() {
  return `e2e-${Date.now()}-${Math.floor(Math.random() * 1000)}@exemplo.com`
}

const SENHA = 'senha-bem-grande'

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
  await expect(page.getByRole('heading', { name: 'Mapa do bloco 31–40' })).toBeVisible()
  return email
}

test('do cadastro à primeira revisão', async ({ page }) => {
  await test.step('cria a conta', async () => {
    await criarConta(page, 'Jeferson')
  })

  await test.step('o conteúdo das dez aulas vem da API', async () => {
    await expect(page.locator('.arow')).toHaveCount(10)
    await page.getByRole('link', { name: /It's Unbelievable/ }).first().click()
    await expect(page.getByRole('heading', { name: "It's Unbelievable!" })).toBeVisible()
    await expect(page.getByText('Prefixos negativos').first()).toBeVisible()
  })

  await test.step('errar um exercício de vocabulário põe a palavra no deck', async () => {
    const exercicio = page.locator('.ex').filter({ hasText: 'honest' }).first()
    await exercicio.getByRole('textbox').fill('resposta errada')
    await exercicio.getByRole('button', { name: 'Verificar' }).click()
    await expect(exercicio.getByText('Ainda não')).toBeVisible()

    // O contador de revisão aparece na trilha.
    await expect(page.locator('a[href="/revisar"] .badge')).toHaveText('1')
  })

  await test.step('revisar a carta e reagendá-la', async () => {
    await page.getByRole('link', { name: /Revisar/ }).click()
    await expect(page.locator('.carta-termo')).toHaveText('dishonest')
    // A tradução não aparece antes de virar.
    await expect(page.locator('.carta-traducao')).toHaveCount(0)

    await page.keyboard.press(' ')
    await expect(page.locator('.carta-traducao')).toHaveText('desonesto')

    await page.keyboard.press('3') // "Bom"
    await expect(page.getByText(/dishonest volta amanhã/)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Nada para revisar agora' })).toBeVisible()
  })

  await test.step('marcar a aula semeia o vocabulário inteiro', async () => {
    await page.getByRole('button', { name: 'Marcar aula 39 como estudada' }).click()
    await expect(page.locator('.prog-top')).toContainText('1/10')
    // 13 itens na aula 39, menos o `dishonest` que já foi revisado hoje.
    await expect(page.locator('a[href="/revisar"] .badge')).toHaveText('12')
  })

  await test.step('o progresso sobrevive ao recarregar', async () => {
    await page.reload()
    await expect(page.locator('.prog-top')).toContainText('1/10')
    await expect(page.locator('a[href="/revisar"] .badge')).toHaveText('12')
  })
})

test('acertar não enche o deck', async ({ page }) => {
  await criarConta(page, 'Certeira')

  await page.goto('/aulas/39')
  await expect(page.getByRole('heading', { name: "It's Unbelievable!" })).toBeVisible()
  const exercicio = page.locator('.ex').filter({ hasText: 'honest' }).first()
  await exercicio.getByRole('textbox').fill('dishonest')
  await exercicio.getByRole('button', { name: 'Verificar' }).click()
  await expect(exercicio.getByText('Correto')).toBeVisible()

  await expect(page.locator('a[href="/revisar"] .badge')).toHaveCount(0)
})

test('a jornada guiada retoma e conclui a aula 31', async ({ page }) => {
  await criarConta(page, 'Estudante guiada')

  await page.goto('/aulas/31')
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
  await page.goto('/aulas/31/estudar')
  await expect(page.getByText('Etapa 2 de 5')).toBeVisible()

  await page.getByRole('button', { name: /Concluir e ir para Estudar/ }).click()
  await page.getByRole('button', { name: /Concluir e ir para Praticar/ }).click()
  const practice = page.locator('.ex').first()
  await practice.getByRole('button', { name: 'Dica 1' }).click()
  await expect(practice.getByText('Pense no comparativo curto do adjetivo')).toBeVisible()
  await practice.getByRole('textbox').fill('more fast')
  await practice.getByRole('button', { name: 'Verificar' }).click()
  await expect(practice.getByText('Ainda não')).toBeVisible()
  await expect(practice.getByText(/palavra ou estrutura a mais/)).toBeVisible()
  await practice.getByRole('button', { name: 'Dica 2' }).click()
  await expect(practice.getByText(/Adicione a terminação/)).toBeVisible()
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
  await expect(page.locator('.prog-top')).toContainText('1/10')
})

test('a correção acontece no servidor: o gabarito não viaja antes', async ({ request }) => {
  // Direto no contrato, sem depender de quando o browser dispara a chamada.
  for (const rota of ['/api/lessons/31', '/api/lessons/39', '/api/exercises?lesson=31']) {
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
  const lesson = await (await request.get('/api/lessons/32')).json()

  expect(lesson.versions[0]).toMatchObject({
    version: 1,
    status: 'reviewed',
    learning_strategy: 'monitorar',
  })
  expect(lesson.content_sources).toEqual(
    expect.arrayContaining([expect.objectContaining({ kind: 'official', publisher: 'VOA Learning English' })]),
  )
  expect(lesson.media[0].cues).toHaveLength(4)

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
  const lesson = await (await request.get('/api/lessons/31')).json()
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
  await page.getByRole('link', { name: 'Caderno' }).click()
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

  await page.goto('/aulas/31')
  const exercise = page.locator('.ex').first()
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
  await page.goto('/aulas/31')

  const exercise = page.locator('.ex').first()
  await exercise.getByRole('textbox').fill('more fast')
  await exercise.getByRole('button', { name: 'Verificar' }).click()
  await expect(exercise.getByText('Ainda não')).toBeVisible()

  await page.getByRole('link', { name: /Revisar/ }).click()
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

test('PWA mantém a aula e sincroniza uma tentativa feita offline', async ({ page, context }) => {
  await criarConta(page, 'Offline E2E')
  await page.goto('/aulas/31')
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Pular para o conteúdo' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()

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
  await page.reload()
  await expect(page.getByText(/Você está offline/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()

  const exercise = page.locator('.ex').first()
  await exercise.getByRole('textbox').fill('faster')
  await exercise.getByRole('button', { name: 'Verificar' }).click()
  await expect(exercise.getByText('Na fila')).toBeVisible()
  await expect(page.getByText(/1 tentativa na fila/)).toBeVisible()

  const synchronized = page.waitForResponse(
    (response) =>
      response.url().includes('/api/exercises/') &&
      response.url().endsWith('/attempt') &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  await context.setOffline(false)
  await synchronized
  await expect(page.getByText('1 tentativa foi sincronizada.')).toBeVisible()
})

test('sem sessão, a aplicação pede login', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()
  // Rota interna também cai no login.
  await page.goto('/revisar')
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()
})

test('painel e aula não têm violações WCAG sérias ou críticas', async ({ page }) => {
  await criarConta(page, 'Acessibilidade E2E')

  const painel = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(painel.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical'))
    .toEqual([])

  await page.goto('/aulas/32')
  await expect(page.getByRole('heading', { name: 'Welcome to the Treehouse!' })).toBeVisible()
  const aula = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(aula.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical'))
    .toEqual([])
})
