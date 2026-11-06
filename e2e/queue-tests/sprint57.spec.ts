import { expect, test } from '@playwright/test'
import type { PositionSync } from '../../frontend/src/features/media/positionSync'

declare global {
  interface Window { PositionSync: typeof PositionSync }
}

test('falha persistente sobrevive à recarga e outra aba retoma com a mesma chave', async ({ context, page }) => {
  let recovered = false
  const received: string[] = []
  await context.route('http://127.0.0.1:5197/api/**', async (route) => {
    const key = route.request().postDataJSON().idempotency_key as string
    received.push(key)
    await route.fulfill(key === 'first' && !recovered
      ? { status: 503, json: { detail: 'synthetic' } }
      : { json: { attempt_id: key === 'first' ? 1 : 2, correct: true } })
  })
  await page.goto('/test-fixtures/offline-queue.html')
  await page.waitForFunction(() => window.queueReady)
  await page.evaluate(async () => {
    for (const [key, exerciseId] of [['first', 1], ['second', 2]] as const) {
      await window.queue.queueAttempt({ userId: 7, exerciseId, answer: 'preserved',
        idempotencyKey: key, createdAt: '2026-11-05T12:00:00Z' })
    }
    await window.queue.syncAttemptQueue(7)
    await window.queue.syncAttemptQueue(7)
  })
  await page.reload()
  await page.waitForFunction(() => window.queueReady)
  expect(await page.evaluate(() => window.queue.syncAttemptQueue(7))).toMatchObject({ synced: 1, blocked: 1 })
  expect(received).toEqual(['first', 'first', 'first', 'second'])
  recovered = true
  const other = await context.newPage()
  await other.goto('/test-fixtures/offline-queue.html')
  await other.waitForFunction(() => window.queueReady)
  expect(await other.evaluate(async () => {
    await window.queue.resumeQueuedAttempt(7, 'first')
    return window.queue.syncAttemptQueue(7)
  })).toMatchObject({ synced: 1, pending: 0, blocked: 0 })
  expect(received.at(-1)).toBe('first')
  expect(await page.evaluate(() => window.queue.listQueuedAttempts(7))).toEqual([])
})

test('posições offline são combinadas e reabertura preserva a posição e a conclusão', async ({ page }) => {
  await page.goto('/test-fixtures/offline-queue.html')
  await page.waitForFunction(() => window.queueReady)
  const state = await page.evaluate(async () => {
    const transport = { allowed: () => false,
      read: async () => { throw new Error('No network in fixture') },
      save: async () => { throw new Error('No network in fixture') } }
    const first = new window.PositionSync(7, 9, transport)
    for (let at = 5; at <= 300; at += 5) await first.record(at)
    return new window.PositionSync(7, 9, transport).snapshot()
  })
  expect(state).toMatchObject({ position: 300, pending: 1 })
  await page.reload()
  await page.waitForFunction(() => window.queueReady)
  expect(await page.evaluate(async () => {
    const transport = { allowed: () => false,
      read: async () => { throw new Error('No network in fixture') },
      save: async () => { throw new Error('No network in fixture') } }
    const reopened = new window.PositionSync(7, 9, transport)
    await reopened.record(0, true)
    return reopened.snapshot()
  })).toMatchObject({ position: 0, completed: true, pending: 2 })
})
