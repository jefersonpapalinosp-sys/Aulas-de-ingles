import AxeBuilder from '@axe-core/playwright'
import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'
import { criarConta, SENHA, expectNoHorizontalScroll } from '../journey-helpers'

async function open(page: Page) {
  const email = await criarConta(page, 'Listening retomada')
  await page.goto('/listening/hotel-riverside')
  await page.getByRole('button', { name: 'Iniciar prática' }).click()
  await expect(page).toHaveURL(/sessao=\d+/)
  await expect(page.getByText('Posição confirmada na conta.')).toBeVisible()
  await expect.poll(() => page.locator('audio').evaluate((audio: HTMLAudioElement) => audio.readyState)).toBeGreaterThan(0)
  return email
}
const question = (page: Page) => page.getByRole('region', { name: '1. How many nights is Alex staying?', exact: true })
async function credentials(page: Page, email: string) {
  const login = await page.request.post('/api/auth/login', { data: { email, password: SENHA } })
  expect(login.status()).toBe(200)
  return { Authorization: `Bearer ${(await login.json()).access_token}` }
}

test('retoma áudio e rascunho, histórico distingue primeira nota da repetição', async ({ page }, info) => {
  await open(page)
  await page.getByRole('button', { name: '+5 s', exact: true }).click()
  await expect(page.getByText('Posição confirmada na conta.')).toBeVisible()
  await question(page).getByLabel('One', { exact: true }).check()
  await expect(question(page).getByText('Rascunho salvo neste dispositivo.')).toBeVisible()
  await page.reload()
  await expect(question(page).getByLabel('One', { exact: true })).toBeChecked()
  await expect.poll(() => page.locator('audio').evaluate((audio: HTMLAudioElement) => audio.currentTime)).toBeGreaterThanOrEqual(4.9)
  await question(page).getByRole('button', { name: 'Confirmar resposta' }).click()
  await expect(question(page).getByText(/Resposta incorreta/)).toBeVisible()
  await question(page).getByLabel('Two', { exact: true }).check()
  await question(page).getByRole('button', { name: 'Responder novamente' }).click()
  await expect(question(page).getByText(/Resposta correta/)).toBeVisible()
  await page.getByRole('link', { name: 'Voltar ao listening rápido' }).click()
  const history = page.getByRole('region', { name: 'Histórico de listening nativo' })
  await expect(history.getByText('Primeiras respostas: 0/4. Últimas tentativas: 1/4.')).toBeVisible()
  await expect(history.getByRole('link', { name: /Continuar de onde parei/ })).toBeVisible()
  expect((await new AxeBuilder({ page }).include('#main-content').analyze()).violations).toEqual([])
  await expectNoHorizontalScroll(page)
  await history.screenshot({ path: info.outputPath('listening-history.png') })
  await history.getByRole('link', { name: 'Revisar erros', exact: true }).click()
  await expect(page.getByRole('group', { name: 'Sua resposta' })).toHaveCount(1)
})

test('resposta offline sobrevive à recarga e reconecta sem duplicar', async ({ page, context }) => {
  const email = await open(page)
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
    if (!navigator.serviceWorker.controller) await new Promise<void>(resolve =>
      navigator.serviceWorker.addEventListener('controllerchange', () => resolve(), { once: true }))
  })
  // As rotas lazy precisam ser visitadas com o worker controlando o documento.
  // Simula perda do cache público; a visita online deve reconstruir o shell validado.
  await page.evaluate(async () => {
    for (const name of await caches.keys()) if (name.endsWith('-shell')) await caches.delete(name)
  })
  const controlled = await page.reload()
  expect(controlled?.fromServiceWorker()).toBe(true)
  await expect(question(page).getByLabel('Two', { exact: true })).toBeVisible()
  expect(await page.evaluate(async () => {
    const names = (await caches.keys()).filter(name => name.endsWith('-shell'))
    return (await Promise.all(names.map(async name => Boolean(await (await caches.open(name)).match('/'))))).some(Boolean)
  })).toBe(true)
  const url = page.url()
  await context.setOffline(true)
  try {
    await question(page).getByLabel('Two', { exact: true }).check()
    await question(page).getByRole('button', { name: 'Confirmar resposta' }).click()
    await expect(page.getByText('1 resposta(s) pendente(s) de envio.', { exact: true })).toBeVisible()
    try { await page.reload() } catch (error) {
      for (const worker of context.serviceWorkers()) {
        console.log('offline-worker', await worker.evaluate(async () => {
          const names = (await caches.keys()).filter(name => name.endsWith('-shell'))
          return Promise.all(names.map(async name => ({ name,
            entries: await Promise.all((await (await caches.open(name)).keys()).map(async key => ({
              path: new URL(key.url).pathname,
              at: (await (await caches.open(name)).match(key))?.headers.get('X-Aulas-Cached-At'), now: Date.now(),
            }))),
          })))
        }).catch(() => 'worker-unavailable'))
      }
      throw error
    }
    await expect(page.getByText('1 resposta(s) pendente(s) de envio.', { exact: true })).toBeVisible()
    await expect(question(page).getByText(/Resposta correta/)).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Revelar transcrição como apoio' })).toBeDisabled()
  } finally { await context.setOffline(false) }
  // O perfil local precisa ser confirmado pelo bootstrap antes do envio.
  await page.reload()
  await expect(question(page).getByText(/Resposta correta/)).toBeVisible()
  await expect(page).toHaveURL(url)
  const headers = await credentials(page, email)
  const exported = await (await page.request.get('/api/me/export', { headers })).json()
  expect(exported.native_listening_responses).toHaveLength(1)
  expect(exported.native_listening_responses[0].payload.selected_ids).toEqual(['two'])
})

test('duas abas preservam rascunhos concorrentes e compartilham confirmação', async ({ page, context }) => {
  await open(page)
  const second = await context.newPage()
  await second.goto(page.url())
  await expect(question(second).getByLabel('Two', { exact: true })).toBeVisible()
  await Promise.all([
    question(page).getByLabel('One', { exact: true }).check(),
    question(second).getByLabel('Two', { exact: true }).check(),
  ])
  await expect(question(page).getByText(/Rascunhos de outras edições/)).toBeVisible()
  await question(second).getByRole('button', { name: 'Confirmar resposta' }).click()
  await expect(question(second).getByText(/Resposta correta/)).toBeVisible()
  await expect(question(page).getByText(/Resposta correta/)).toBeVisible()
  await expect(question(page).getByLabel('One', { exact: true })).toBeChecked()
  await second.close()
})

test('conflito preserva seleção até reenvio explícito, exportação e exclusão incluem posição', async ({ page }) => {
  const email = await open(page)
  await page.getByRole('button', { name: '+5 s', exact: true }).click()
  await expect(page.getByText('Posição confirmada na conta.')).toBeVisible()
  const id = Number(new URL(page.url()).searchParams.get('sessao'))
  const headers = await credentials(page, email)
  expect((await page.request.post(`/api/listening/sessions/${id}/responses`, { headers, data: {
    kind: 'answer', question_id: 'stay', selected_ids: ['one'], expected_revision: 0, operation_key: randomUUID(),
  } })).status()).toBe(200)
  await question(page).getByLabel('Two', { exact: true }).check()
  await question(page).getByRole('button', { name: 'Confirmar resposta' }).click()
  await expect(page.getByText(/a sessão mudou em outra aba/)).toBeVisible()
  await page.getByRole('button', { name: 'Enviar como nova tentativa' }).click()
  await expect(question(page).getByText(/Repetição: a nota inicial foi mantida/)).toBeVisible()
  const exported = await (await page.request.get('/api/me/export', { headers })).json()
  expect(exported.native_listening_positions[0].position_seconds).toBe(5)
  expect(exported.native_listening_responses).toHaveLength(2)
  expect(exported.native_listening_sessions[0].revision).toBe(2)
  const deleted = await page.request.delete('/api/me/account', { headers, data: {
    password: SENHA, confirmation: 'EXCLUIR MINHA CONTA', operation_key: randomUUID(),
  } })
  expect(deleted.status()).toBe(202)
  expect((await page.request.get(`/api/listening/sessions/${id}/position`, { headers })).status()).toBe(401)
})

test('trocar conta não envia a pendência de outro aluno e voltar recupera a resposta', async ({ page }) => {
  const email = await open(page)
  const url = page.url()
  await page.route('**/api/listening/sessions/*/responses', route => route.abort())
  await question(page).getByLabel('Two', { exact: true }).check()
  await question(page).getByRole('button', { name: 'Confirmar resposta' }).click()
  await expect(page.getByRole('button', { name: 'Tentar enviar novamente' })).toBeVisible()
  const otherEmail = `s61-other-${randomUUID()}@example.com`
  const other = await page.request.post('/api/auth/register', { data: { email: otherEmail, password: SENHA, display_name: 'Outra conta' } })
  expect(other.status()).toBe(201)
  await page.unroute('**/api/listening/sessions/*/responses')
  await page.reload()
  // Cookie de outra conta não confirma automaticamente o perfil local anterior.
  await page.getByLabel('E-mail').fill(otherEmail)
  await page.getByLabel('Senha').fill(SENHA)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByLabel('E-mail')).toHaveCount(0)
  await page.goto(url)
  await expect(page.getByText('Não foi possível abrir a atividade ou a sessão.')).toBeVisible()
  await expect(page.getByRole('group', { name: 'Sua resposta' })).toHaveCount(0)
  const otherHeaders = await credentials(page, otherEmail)
  const exported = await (await page.request.get('/api/me/export', { headers: otherHeaders })).json()
  expect(exported.native_listening_responses).toHaveLength(0)
  await credentials(page, email)
  await page.reload()
  await page.getByLabel('E-mail').fill(email)
  await page.getByLabel('Senha').fill(SENHA)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByLabel('E-mail')).toHaveCount(0)
  await page.goto(url)
  await expect(question(page).getByText(/Resposta correta/)).toBeVisible()
})

test('histórico paginado mede latência sem carregar todas as respostas', async ({ page }) => {
  const email = await open(page)
  const headers = await credentials(page, email)
  for (let n = 0; n < 11; n++) {
    expect((await page.request.post('/api/listening/native/hotel-riverside/sessions', { headers,
      data: { version: 1, operation_key: randomUUID() } })).status()).toBe(200)
  }
  const samples: number[] = []
  for (let n = 0; n < 12; n++) {
    const start = performance.now()
    const response = await page.request.get('/api/listening/history?limit=10', { headers })
    expect(response.status()).toBe(200)
    const data = await response.json()
    samples.push(performance.now() - start)
    expect(data.items).toHaveLength(10)
    expect(data.attempts).toBe(12)
    const next = await (await page.request.get(`/api/listening/history?limit=10&before=${data.next_before}`, { headers })).json()
    expect(next.items).toHaveLength(2)
    expect(next.next_before).toBeNull()
  }
  samples.sort((a, b) => a - b)
  console.log(JSON.stringify({ listening_history_ms: { median: samples[6], p95: samples[11], samples: 12, sessions: 12 } }))
})
