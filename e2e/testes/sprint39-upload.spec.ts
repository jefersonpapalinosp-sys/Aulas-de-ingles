import { randomUUID } from 'node:crypto'
import { request as httpRequest } from 'node:http'
import { expect, test, type Page } from '@playwright/test'
import { assertTarget } from '../safety.mjs'
import { silentWav } from '../audio-fixture'

const path = '/cursos/voa-level-1/aulas/31/estudar/revisar'
async function account(page: Page) {
  const response = await page.request.post('/api/auth/register', { data: {
    email: `s39b-${randomUUID()}@example.com`, password: 'synthetic-long-password', display_name: 'Upload probe',
  } })
  expect(response.status()).toBe(201)
  return { Authorization: `Bearer ${(await response.json()).access_token}` }
}

async function fakeRecorder(page: Page, delayed = false) {
  await page.addInitScript(({ delayed, wav }) => {
    const state = { stops: 0, grant: () => {} }
    Object.assign(window, { voiceProbe: state })
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: () => new Promise((resolve) => {
        state.grant = () => resolve({ getTracks: () => [{ stop: () => { state.stops++ } }] })
        if (!delayed) state.grant()
      }),
    } })
    class Recorder {
      static isTypeSupported() { return true }
      state = 'inactive'
      mimeType = 'audio/wav'
      ondataavailable: ((event: { data: Blob }) => void) | null = null
      onstop: (() => void) | null = null
      start() { this.state = 'recording' }
      stop() {
        this.state = 'inactive'
        this.ondataavailable?.({ data: new Blob([new Uint8Array(wav)], { type: 'audio/wav' }) })
        this.onstop?.()
      }
    }
    Object.assign(window, { MediaRecorder: Recorder })
  }, { delayed, wav: Array.from(silentWav(1644)) })
}

test('Sprint 39B: política e Nginx aceitam o limite decimal, inclusive chunked', async ({ page, baseURL }) => {
  const headers = await account(page)
  const policy = await (await page.request.get('/api/speaking/policy')).json()
  expect(policy.max_bytes).toBe(2_000_000)
  const lesson = await (await page.request.get('/api/lessons/31')).json()
  const create = async () => {
    const result = await page.request.post('/api/speaking/attempts', { headers, data: {
      cue_id: lesson.media[0].cues[0].id, duration_ms: 10_416, consent: true,
    } })
    expect(result.status()).toBe(201)
    return `/api/speaking/attempts/${(await result.json()).id}/audio`
  }
  // WAV PCM estéreo sintético: ~10,4 s, sem voz pessoal.
  const wav = silentWav(policy.max_bytes, 48_000, 2)
  const url = await create()
  for (let retry = 0; retry < 2; retry++) {
    expect((await page.request.put(url, { headers: { ...headers, 'Content-Type': 'audio/wav' }, data: wav })).status()).toBe(200)
  }
  const chunked = async (url: string, data: Buffer) => new Promise<number>((resolve, reject) => {
    const req = httpRequest(new URL(url, assertTarget(baseURL)), {
      method: 'PUT', headers: { ...headers, 'Content-Type': 'audio/wav' }, timeout: 15_000,
    }, (response) => { response.resume(); response.on('end', () => resolve(response.statusCode!)) })
    req.on('error', reject); req.on('timeout', () => req.destroy(new Error('timeout')))
    req.write(data.subarray(0, 1_000_000)); req.end(data.subarray(1_000_000))
  })
  expect(await chunked(await create(), wav)).toBe(200)
  const oversized = Buffer.concat([wav, Buffer.from([0])])
  expect((await page.request.put(await create(), { headers: { ...headers, 'Content-Type': 'audio/wav' }, data: oversized })).status()).toBe(413)
  expect(await chunked(await create(), oversized)).toBe(413)
})

test('Sprint 39B: resposta perdida não apaga áudio nem duplica tentativa ao tentar novamente', async ({ page }) => {
  const headers = await account(page)
  await fakeRecorder(page)
  const loaded: string[] = []
  page.on('request', (request) => { loaded.push(request.url()) })
  await page.goto('/inicio')
  await expect(page.getByRole('heading', { name: 'Hoje', exact: true })).toBeVisible()
  expect(loaded.some((url) => url.includes('/assets/lesson-study-'))).toBe(false)
  await page.goto(path)
  await page.getByRole('button', { name: '2. Gravar minha voz' }).click()
  await page.getByRole('button', { name: 'Parar gravação' }).click()
  await page.getByRole('checkbox', { name: /Concordo em salvar/ }).check()
  let uploads = 0
  await page.route('**/api/speaking/attempts/*/audio', async (route) => {
    if (route.request().method() !== 'PUT' || uploads++ > 0) { await route.continue(); return }
    const saved = await route.fetch()
    expect(saved.status()).toBe(200)
    await route.abort('failed') // Servidor salvou; a resposta não chega ao componente.
  })
  await page.getByRole('button', { name: 'Salvar na minha conta' }).click()
  await expect(page.getByText(/O áudio continua nesta tela; você pode baixá-lo/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Baixar gravação local' })).toBeVisible()
  await page.getByRole('button', { name: 'Salvar na minha conta' }).click()
  await expect(page.getByText(/Gravação salva na sua conta/)).toBeVisible()
  const list = await (await page.request.get('/api/speaking/attempts', { headers })).json()
  expect(list).toHaveLength(1)
})

test('Sprint 39B: microfone aceito depois de trocar etapa é encerrado', async ({ page }) => {
  await account(page)
  await fakeRecorder(page, true)
  await page.goto(path)
  await page.getByRole('button', { name: '2. Gravar minha voz' }).click()
  await expect(page.getByRole('button', { name: 'Cancelar acesso ao microfone' })).toBeVisible()
  await page.getByRole('link', { name: /Preparar/ }).first().click()
  await expect(page).toHaveURL(/\/preparar$/)
  await page.evaluate(() => (window as unknown as { voiceProbe: { grant: () => void } }).voiceProbe.grant())
  await expect.poll(() => page.evaluate(() => (window as unknown as { voiceProbe: { stops: number } }).voiceProbe.stops)).toBe(1)
  await expect(page.getByRole('button', { name: 'Parar gravação' })).toHaveCount(0)
})

test('Sprint 39C: tipo falso e duração real excessiva não publicam a tentativa', async ({ page }) => {
  const headers = await account(page)
  const policy = await (await page.request.get('/api/speaking/policy')).json()
  expect(policy.content_validation).toBe('decoded_audio_v1')
  const lesson = await (await page.request.get('/api/lessons/31')).json()
  const attempt = await (await page.request.post('/api/speaking/attempts', { headers, data: {
    cue_id: lesson.media[0].cues[0].id, duration_ms: 1, consent: true,
  } })).json()
  const url = `/api/speaking/attempts/${attempt.id}/audio`
  expect((await page.request.put(url, { headers: { ...headers, 'Content-Type': 'audio/mp4' }, data: silentWav() })).status()).toBe(415)
  expect((await page.request.put(url, { headers: { ...headers, 'Content-Type': 'audio/wav' }, data: silentWav(31 * 32000 + 44) })).status()).toBe(422)
  expect(await (await page.request.get('/api/speaking/attempts', { headers })).json()).toEqual([])
  const saved = await page.request.put(url, { headers: { ...headers, 'Content-Type': 'audio/wav' }, data: silentWav() })
  expect(saved.status()).toBe(200)
  expect((await saved.json()).duration_ms).toBe(1000) // Ignora o 1 ms declarado.
})
