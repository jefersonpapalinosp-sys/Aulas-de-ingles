import { expect, test, type Page } from '@playwright/test'
import type * as Queue from '../../frontend/src/features/offline/attemptQueue'

declare global {
  interface Window {
    queue: typeof Queue
    queueReady: boolean
    queueEvents: Array<{ kind: string; detail: unknown }>
  }
}

async function open(page: Page) {
  await page.goto('/test-fixtures/offline-queue.html')
  await page.waitForFunction(() => window.queueReady === true)
}

async function enqueue(page: Page, start: number, count: number) {
  return page.evaluate(async ({ start, count }) => {
    await Promise.all(Array.from({ length: count }, (_, n) => window.queue.queueAttempt({
      userId: 7, exerciseId: start + n + 1, answer: `answer-${start + n}`,
      idempotencyKey: `key-${start + n}`, createdAt: '2026-10-13T10:00:00Z',
      sessionId: 44, courseSlug: 'voa-level-2', lessonNumber: 6,
    })))
  }, { start, count })
}

test('duas abas preservam 100 respostas e serializam a sincronização por chave', async ({ context, page }) => {
  const other = await context.newPage()
  const requests: string[] = []
  await context.route('http://127.0.0.1:5197/api/**', async (route) => {
    expect(route.request().url()).toMatch(/\/api\/exercises\/\d+\/attempt$/)
    const body = route.request().postDataJSON()
    requests.push(body.idempotency_key)
    expect(body.practice_session_id).toBe(44)
    await route.fulfill({ json: { attempt_id: requests.length, correct: true } })
  })
  await Promise.all([open(page), open(other)])
  await Promise.all([enqueue(page, 0, 50), enqueue(other, 50, 50)])
  expect(await page.evaluate(() => window.queue.listQueuedAttempts(7))).toHaveLength(100)
  expect(await other.evaluate(() => window.queue.listQueuedAttempts(7))).toHaveLength(100)
  const extra = await page.evaluate(async () => {
    try {
      await window.queue.queueAttempt({ userId: 7, exerciseId: 102, answer: 'extra', idempotencyKey: 'extra', createdAt: '2026-10-13T10:00:00Z' })
      return 'accepted'
    } catch (err) { return (err as Error).message }
  })
  expect(extra).toContain('atingiu 100')
  const results = await Promise.all([
    page.evaluate(() => window.queue.syncAttemptQueue(7)),
    other.evaluate(() => window.queue.syncAttemptQueue(7)),
  ])
  expect(results.reduce((total, item) => total + item.synced, 0)).toBe(100)
  expect(requests).toHaveLength(100)
  expect(new Set(requests).size).toBe(100)
  expect(await other.evaluate(() => window.queue.listQueuedAttempts(7))).toHaveLength(0)
  await expect.poll(() => other.evaluate(() => window.queueEvents.some((event) => event.kind === 'sync'))).toBe(true)
})

test('fechar a aba com envio em curso libera o lock e conserva idempotência', async ({ context, page }) => {
  const other = await context.newPage()
  const committed = new Map<string, number>()
  const received: string[] = []
  let release!: () => void
  const held = new Promise<void>((resolve) => { release = resolve })
  await context.route('http://127.0.0.1:5197/api/**', async (route) => {
    const key = route.request().postDataJSON().idempotency_key as string
    received.push(key)
    if (!committed.has(key)) committed.set(key, committed.size + 1)
    if (received.length === 1) await held
    await route.fulfill({ json: { attempt_id: committed.get(key), correct: true } }).catch(() => undefined)
  })
  await Promise.all([open(page), open(other)])
  await enqueue(page, 0, 1)
  const first = page.evaluate(() => window.queue.syncAttemptQueue(7)).catch(() => undefined)
  await expect.poll(() => received.length).toBe(1)
  await page.close()
  release()
  await first
  expect((await other.evaluate(() => window.queue.syncAttemptQueue(7))).synced).toBe(1)
  expect(received).toEqual(['key-0', 'key-0'])
  expect(committed.size).toBe(1)
  expect(await other.evaluate(() => window.queue.listQueuedAttempts(7))).toHaveLength(0)
})

test('migração concorrente e eventos de outra aba não ressuscitam a cópia antiga', async ({ context, page }) => {
  const other = await context.newPage()
  await context.route('http://127.0.0.1:5197/api/**', (route) => route.fulfill({ json: { attempt_id: 1, correct: true } }))
  await Promise.all([open(page), open(other)])
  await page.evaluate(() => {
    localStorage.setItem(window.queue.LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify([
      { userId: 7, exerciseId: 1, answer: 'legacy', idempotencyKey: 'old', createdAt: '2026-10-13T10:00:00Z' },
    ]))
  })
  const rows = await Promise.all([
    page.evaluate(() => window.queue.listQueuedAttempts(7)),
    other.evaluate(() => window.queue.listQueuedAttempts(7)),
  ])
  expect(rows.map((items) => items.length)).toEqual([1, 1])
  await page.evaluate(() => window.queue.syncAttemptQueue(7))
  await other.evaluate(() => {
    const raw = JSON.parse(localStorage.getItem(window.queue.LEGACY_ATTEMPT_QUEUE_STORAGE_KEY)!)
    raw.push({ userId: 7, exerciseId: 2, answer: 'new from old tab', idempotencyKey: 'old-2', createdAt: '2026-10-13T10:00:00Z' })
    localStorage.setItem(window.queue.LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify(raw))
  })
  expect((await page.evaluate(() => window.queue.listQueuedAttempts(7))).map((item) => item.idempotencyKey)).toEqual(['old-2'])
  await expect.poll(() => other.evaluate(() => window.queueEvents.some((event) => event.kind === 'sync'))).toBe(true)
  await page.reload()
  await page.waitForFunction(() => window.queueReady)
  expect((await page.evaluate(() => window.queue.listQueuedAttempts(7))).map((item) => item.idempotencyKey)).toEqual(['old-2'])
})
