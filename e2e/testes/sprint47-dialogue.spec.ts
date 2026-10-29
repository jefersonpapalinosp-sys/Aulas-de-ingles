import { randomUUID } from 'node:crypto'
import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Locator, type Page } from '@playwright/test'
import { configureGateway, gatewayCalls, type Scenario } from '../gateway-fixture'

// Entrada de áudio sintética do Chromium; MediaRecorder, upload, API, fila,
// worker e HTTP do provedor são reais. Nenhuma rota /api é interceptada.
test.use({
  permissions: ['microphone'],
  serviceWorkers: 'block', // PWA tem suíte própria; aqui observamos o HTTP da conversa.
  launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] },
})
test.beforeEach(async () => {
  await expect.poll(() => {
    try { configureGateway(); return true } catch { return false }
  }).toBe(true)
})

async function open(page: Page, mode = 'guided') {
  await page.addInitScript(() => {
    // Só observa o evento nativo: não fabrica bytes nem simula MediaRecorder.
    const Recorder = window.MediaRecorder
    window.MediaRecorder = class extends Recorder {
      constructor(stream: MediaStream, options?: MediaRecorderOptions) {
        super(stream, options)
        this.addEventListener('start', () => Object.assign(window, { e2eRecorderStarted: true }))
      }
    }
  })
  const registered = await page.request.post('/api/auth/register', { data: {
    email: `dialogue-${randomUUID()}@example.com`, password: 'synthetic-dialogue-password',
    display_name: 'Dialogue E2E',
  } })
  expect(registered.status()).toBe(201)
  const headers = { Authorization: `Bearer ${(await registered.json()).access_token}` }
  await page.goto('/cursos/voa-level-1/aulas/31/estudar/revisar')
  await page.getByRole('button', { name: 'Abrir parceiro de conversa' }).click()
  const workspace = page.locator('.dialogue-workspace')
  await workspace.getByRole('combobox', { name: 'Modo', exact: true }).selectOption(mode)
  const response = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/speaking/dialogues'))
  await workspace.getByRole('button', { name: 'Iniciar conversa' }).click()
  const created = await response
  expect(created.status()).toBe(201)
  const conversation = await created.json()
  return { workspace, headers, id: conversation.id as number }
}

async function sendText(page: Page, workspace: Locator, id: number, position = 1) {
  const response = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/dialogues/${id}/turns/${position}/text`))
  await workspace.getByLabel('Sua resposta em inglês').fill('The train is faster than the bus.')
  await workspace.getByRole('button', { name: 'Enviar texto' }).click()
  const accepted = await response
  expect(accepted.status()).toBe(202)
  return { result: await accepted.json() }
}

async function sendAudio(page: Page, workspace: Locator, id: number, position: number) {
  await page.evaluate(() => Object.assign(window, { e2eRecorderStarted: false }))
  await workspace.getByRole('button', { name: 'Gravar resposta' }).click()
  await page.waitForFunction(() => (window as unknown as { e2eRecorderStarted: boolean }).e2eRecorderStarted)
  // O gravador precisa de amostras reais para que o decodificador valide o WebM.
  await page.waitForTimeout(1200)
  await workspace.getByRole('button', { name: 'Parar gravação' }).click()
  const send = workspace.getByRole('button', { name: 'Enviar áudio' })
  await expect(send).toBeDisabled()
  await workspace.getByRole('checkbox', { name: /Concordo em salvar e enviar esta gravação ao provedor externo/ }).check()
  const response = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().endsWith(`/dialogues/${id}/turns/${position}/audio`))
  await send.click()
  const accepted = await response
  expect(accepted.status()).toBe(202)
  expect(accepted.request().headers()['x-audio-consent']).toBe('true')
  return accepted
}

test('INFRA-47: texto e áudio atravessam worker/gateway; replay, custo, avaliação e exclusão', async ({ page }, testInfo) => {
  const { workspace, headers, id } = await open(page)
  const text = await sendText(page, workspace, id)
  expect(text.result.job_id).toBeGreaterThan(0)
  await expect(workspace.locator('.dialogue-partner')).toHaveText('What do you do after your trip?')
  await expect(workspace.getByLabel('Sua resposta em inglês')).toBeFocused()
  // A posição identifica o turno: até uma nova chave mantém o job original.
  const replay = await page.request.post(`/api/speaking/dialogues/${id}/turns/1/text`, {
    headers, data: { text: 'The train is faster than the bus.', idempotency_key: randomUUID() },
  })
  expect(replay.status()).toBe(202)
  expect((await replay.json()).job_id).toBe(text.result.job_id)
  await sendAudio(page, workspace, id, 2)
  await expect(workspace.locator('.dialogue-partner')).toHaveCount(2)
  await expect(workspace.locator('.dialogue-turn').nth(1)).toContainText('transcrição incerta')
  await expect(workspace.getByLabel('Sua resposta em inglês')).toBeFocused()
  const saved = await (await page.request.get(`/api/speaking/dialogues/${id}`, { headers })).json()
  expect(saved.turns).toHaveLength(2)
  expect(saved.turns.every((turn: { state: string; fallback: boolean; check_details: unknown }) =>
    turn.state === 'completed' && !turn.fallback && turn.check_details)).toBe(true)
  expect(saved.turns[1].words.find((word: { text: string }) => word.text === 'train').confidence).toBe(0.6)
  const balance = await (await page.request.get('/api/speaking/dialogues/status', { headers })).json()
  expect(balance).toMatchObject({ consumed_today: 2, reserved_today: 0, cost_microusd_today: 17, cost_incomplete: false })
  const calls = gatewayCalls()
  expect(calls.dialogue).toHaveLength(2)
  expect(calls.stt).toHaveLength(1)
  expect(calls.stt[0].bytes).toBeGreaterThan(0)
  expect(calls.stt[0].content_type).toContain('audio/webm')
  expect(new Set(calls.dialogue.map(call => call.key)).size).toBe(2)
  await workspace.locator('.dialogue-turn').first().getByRole('button', { name: 'Foi útil', exact: true }).click()
  await expect(workspace.locator('.dialogue-turn').first().getByRole('button', { name: 'Foi útil', exact: true })).toHaveAttribute('aria-pressed', 'true')
  const exportResponse = await page.request.get('/api/me/export', { headers })
  expect(exportResponse.status()).toBe(200)
  const exported = await exportResponse.json()
  expect(exported.dialogue_turns.map((turn: { cost_microusd: number }) => turn.cost_microusd)).toEqual([7, 10])
  expect(exported.dialogue_turns[0].human_rating).toBe('helpful')
  expect((await new AxeBuilder({ page }).include('.dialogue-workspace').analyze()).violations).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await workspace.screenshot({ path: testInfo.outputPath('dialogue-integrated.png') })
  await workspace.getByRole('button', { name: 'Excluir conversa' }).click()
  await workspace.getByRole('button', { name: 'Confirmar exclusão' }).click()
  await expect(workspace.getByRole('button', { name: 'Iniciar conversa' })).toBeVisible()
  expect((await page.request.get(`/api/speaking/dialogues/${id}`, { headers })).status()).toBe(404)
  expect((await page.request.get('/api/me/export', { headers })).status()).toBe(200)
})

for (const kind of ['dialogue', 'stt']) {
  test(`INFRA-47: ${kind} lento mantém bloqueio do envio até o worker concluir`, async ({ page }) => {
    configureGateway(kind === 'dialogue' ? 'slow' : 'success', kind === 'stt' ? 'slow' : 'success')
    const { workspace, id } = await open(page)
    if (kind === 'dialogue') await sendText(page, workspace, id)
    else await sendAudio(page, workspace, id, 1)
    await expect(workspace.getByText('Aguardando resposta…', { exact: true })).toBeVisible()
    await expect(workspace.getByRole('button', { name: 'Enviar texto' })).toBeDisabled()
    await expect(workspace.locator('.dialogue-partner')).toHaveText('What do you do after your trip?')
    await expect(workspace.getByLabel('Sua resposta em inglês')).toBeEnabled()
    expect(gatewayCalls().dialogue).toHaveLength(1)
    expect(gatewayCalls().stt).toHaveLength(kind === 'stt' ? 1 : 0)
  })
}

for (const mode of ['failure', 'invalid'] as Scenario[]) {
  test(`INFRA-47: diálogo ${mode} usa roteiro sem perder critérios e permite continuar`, async ({ page }) => {
    configureGateway(mode)
    const { workspace, headers, id } = await open(page)
    await sendText(page, workspace, id)
    await expect(workspace.getByText('Resposta do roteiro · assistência indisponível')).toBeVisible()
    await expect(workspace.getByText(/Termos (usados|não identificados):/).first()).toBeVisible()
    const turn = await (await page.request.get(`/api/speaking/dialogues/${id}/turns/1`, { headers })).json()
    expect(turn.state).toBe('completed')
    expect(turn.fallback).toBe(true)
    expect(turn.error_code).toBe(mode === 'failure' ? 'provider_unavailable' : 'invalid_provider_response')
    expect(gatewayCalls().dialogue).toHaveLength(1)
    await workspace.getByRole('button', { name: 'Nova conversa no Roteiro' }).click()
    const created = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/speaking/dialogues'))
    await workspace.getByRole('button', { name: 'Iniciar conversa' }).click()
    const script = await (await created).json()
    await sendText(page, workspace, script.id)
    await expect(workspace.getByText('Resposta do roteiro da aula')).toBeVisible()
    expect(gatewayCalls().dialogue).toHaveLength(1)
  })

  test(`INFRA-47: STT ${mode} encerra espera e deixa continuar por texto`, async ({ page }) => {
    configureGateway('success', mode)
    const { workspace, headers, id } = await open(page)
    await sendAudio(page, workspace, id, 1)
    await expect(workspace.getByRole('alert')).toContainText('Não foi possível processar este turno')
    const turn = await (await page.request.get(`/api/speaking/dialogues/${id}/turns/1`, { headers })).json()
    expect(turn.state).toBe('failed')
    expect(turn.error_code).toBe(mode === 'failure' ? 'provider_unavailable' : 'invalid_provider_response')
    expect(gatewayCalls().stt).toHaveLength(1)
    expect(gatewayCalls().dialogue).toHaveLength(0)
    await sendText(page, workspace, id, 2)
    await expect(workspace.locator('.dialogue-partner')).toHaveText('What do you do after your trip?')
    expect(gatewayCalls().dialogue).toHaveLength(1)
  })
}
