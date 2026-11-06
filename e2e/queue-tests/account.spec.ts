import { expect, test } from '@playwright/test'
import type * as Queue from '../../frontend/src/features/offline/attemptQueue'

declare global {
  interface Window {
    queue: typeof Queue
    queueReady: boolean
  }
}

for (const blockedStorage of ['none', 'indexedDB', 'profile']) {
  test(`exclusão confirmada limpa a conta local e comunica falhas (${blockedStorage})`, async ({ page }) => {
    let deleted = false
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (!path.startsWith('/api/')) { await route.continue(); return }
      if (path === '/api/auth/refresh') {
        await route.fulfill({ json: { access_token: 'synthetic-access', expires_in: 900 } })
      } else if (path === '/api/auth/me') {
        await route.fulfill({ json: { id: 3, email: 'student@example.test', display_name: 'Aluno de teste' } })
      } else if (path === '/api/me/account' && route.request().method() === 'DELETE') {
        deleted = true
        await route.fulfill({ status: 202, json: { database_deleted: true, state: 'cleanup_pending' } })
      } else await route.fulfill({ status: 404, json: {} })
    })
    await page.goto('/test-fixtures/offline-queue.html')
    await page.waitForFunction(() => window.queueReady)
    await page.evaluate(async () => {
      for (const userId of [3, 30]) {
        await window.queue.queueAttempt({ userId, exerciseId: 1, answer: 'private',
          idempotencyKey: `s52-${userId}`, createdAt: new Date().toISOString() })
        localStorage.setItem(`aulas-ingles:writing-draft:v1:${userId}:31`, 'private draft')
        localStorage.setItem(`aulas-ingles:media-position:v2:${userId}:1`, 'position')
      }
      localStorage.setItem('public-preference', 'preserve')
    })
    if (blockedStorage === 'indexedDB') {
      await page.addInitScript(() => {
        indexedDB.open = () => { throw new DOMException('Storage blocked', 'SecurityError') }
      })
    } else if (blockedStorage === 'profile') {
      await page.addInitScript(() => {
        const original = Storage.prototype.removeItem
        Storage.prototype.removeItem = function (key) {
          if (key === 'aulas:last-user:v1') throw new DOMException('Storage blocked', 'SecurityError')
          original.call(this, key)
        }
      })
    }
    page.on('dialog', (dialog) => { void dialog.accept() })
    await page.goto('/test-fixtures/account.html')
    await expect(page.getByLabel('Sessão', { exact: true })).toHaveText('Aluno de teste')
    await page.getByLabel('Senha atual', { exact: true }).fill('senha-correta')
    await page.getByLabel('Digite EXCLUIR MINHA CONTA', { exact: false }).fill('EXCLUIR MINHA CONTA')
    await page.getByRole('button', { name: 'Excluir minha conta definitivamente' }).click()
    await expect(page.getByLabel('Sessão', { exact: true })).toHaveText('sem sessão')
    await expect(page.getByRole('status').filter({ hasText: 'A conta foi excluída.' })).toContainText(blockedStorage !== 'none'
      ? 'Não foi possível concluir a limpeza deste navegador'
      : 'foram removidos deste navegador')
    expect(deleted).toBe(true)
    expect(await page.evaluate(() => ({
      draft: localStorage.getItem('aulas-ingles:writing-draft:v1:3:31'),
      position: localStorage.getItem('aulas-ingles:media-position:v2:3:1'),
      profile: localStorage.getItem('aulas:last-user:v1'),
      other: localStorage.getItem('aulas-ingles:writing-draft:v1:30:31'),
      public: localStorage.getItem('public-preference'),
    }))).toEqual({ draft: null, position: null,
      profile: blockedStorage === 'profile' ? JSON.stringify({ id: 3, display_name: 'Aluno de teste' }) : null,
      other: 'private draft', public: 'preserve' })
    if (blockedStorage !== 'indexedDB') {
      await page.goto('/test-fixtures/offline-queue.html')
      await page.waitForFunction(() => window.queueReady)
      expect(await page.evaluate(() => window.queue.listQueuedAttempts(3))).toEqual([])
      expect(await page.evaluate(() => window.queue.listQueuedAttempts(30))).toHaveLength(1)
    }
  })
}

for (const status of [403, 429]) {
  test(`confirmação recusada (${status}) preserva sessão sem refresh nem reenvio`, async ({ page }) => {
    let refreshes = 0
    let deletions = 0
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (!path.startsWith('/api/')) { await route.continue(); return }
      if (path === '/api/auth/refresh') {
        refreshes++
        await route.fulfill({ json: { access_token: 'synthetic-access', expires_in: 900, token_type: 'bearer' } })
      } else if (path === '/api/auth/me') {
        await route.fulfill({ json: { id: 3, email: 'student@example.test', display_name: 'Aluno de teste' } })
      } else if (path === '/api/me/account' && route.request().method() === 'DELETE') {
        deletions++
        expect(route.request().headers().authorization).toBe('Bearer synthetic-access')
        await route.fulfill({ status, json: { code: 'password_mismatch', detail: 'Senha incorreta.' } })
      } else await route.fulfill({ status: 404, json: { detail: 'Fixture não definida.' } })
    })
    page.on('dialog', (dialog) => { void dialog.accept() })
    await page.goto('/test-fixtures/account.html')
    await expect(page.getByLabel('Sessão', { exact: true })).toHaveText('Aluno de teste')
    await page.getByLabel('Senha atual', { exact: true }).fill('senha-incorreta')
    await page.getByLabel('Digite EXCLUIR MINHA CONTA', { exact: false }).fill('EXCLUIR MINHA CONTA')
    await page.getByRole('button', { name: 'Excluir minha conta definitivamente' }).click()
    await expect(page.getByText(status === 403
      ? 'Senha incorreta. A conta não foi excluída.'
      : 'Muitas tentativas. Aguarde antes de confirmar novamente.', { exact: true })).toBeVisible()
    await expect(page.getByLabel('Sessão', { exact: true })).toHaveText('Aluno de teste')
    expect(refreshes).toBe(1)
    expect(deletions).toBe(1)
  })
}
