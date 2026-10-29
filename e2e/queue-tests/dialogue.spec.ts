import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test(`conversa isolada: texto, polling, fallback, voz e exclusão (${viewport.width}px)`, async ({ page }) => {
    page.on('pageerror', (error) => console.error('PAGE ERROR:', error.message))
    page.on('console', (message) => { if (message.type() === 'error') console.error('BROWSER:', message.text()) })
    await page.setViewportSize(viewport)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.addInitScript(() => {
      const spoken: string[] = []
      Object.assign(window, { __spoken: spoken })
      Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
        cancel() {}, getVoices: () => [{ localService: true, lang: 'en-US', name: 'Synthetic local voice' }],
        speak(utterance: SpeechSynthesisUtterance) { spoken.push(utterance.text); setTimeout(() => utterance.onend?.(new Event('end') as SpeechSynthesisEvent), 10) },
      } })
      Object.defineProperty(window, 'SpeechSynthesisUtterance', { configurable: true, value: class {
        constructor(readonly text: string) {}
      } })
    })
    const status = { enabled: true, guided_enabled: true, audio_enabled: false,
      daily_quota: 12, remaining_today: 12, reserved_today: 0, consumed_today: 0,
      quota_resets_at: '2026-10-29T00:00:00Z', retention_days: 30, cost_microusd_today: 0, cost_incomplete: false }
    const turn = { position: 1, role: 'student', input_kind: 'text', state: 'pending',
      transcript: 'I take the bus.', checks: { target_terms_missing: true, too_short: true, too_long: true },
      check_details: { target_terms: [{ text: 'bus', covered: true }, { text: 'train', covered: false }], grammar_patterns: [] },
      hints: [], partner_text: 'Where do you go?', confidence: 0, fallback: true, error_code: 'provider_unavailable',
      human_rating: null as string | null, job_id: 8, created_at: '2026-10-28T12:00:00Z', completed_at: null, words: [] }
    const dialogue = { id: 7, lesson_id: 31, mode: 'guided', state: 'active', partner_speaker: 'Anna',
      turn_limit: 12, turns_remaining: 12, provider_name: 'synthetic', rubric_version: 'test',
      started_at: '2026-10-28T12:00:00Z', ended_at: null, turns: [] as typeof turn[] }
    let submitted = 0, reads = 0, deleted = false
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
      const request = route.request(), path = new URL(request.url()).pathname
      const json = (body: unknown, code = 200) => route.fulfill({ status: code, json: body })
      if (path.endsWith('/dialogues/status')) return json(status)
      if (request.method() === 'POST' && path.endsWith('/dialogues')) {
        expect(request.postDataJSON().operation_key).toMatch(/^[a-f0-9-]{36}$/)
        return json(dialogue, 201)
      }
      if (request.method() === 'POST' && path.endsWith('/text')) {
        expect(request.postDataJSON().idempotency_key).toMatch(/^[a-f0-9-]{36}$/)
        submitted++; dialogue.turns = [turn]; dialogue.turns_remaining = 11
        return json({ position: 1, state: 'pending', job_id: 8, turns_remaining: 11 }, 202)
      }
      if (request.method() === 'PUT' && path.endsWith('/rating')) {
        turn.human_rating = request.postDataJSON().rating
        return json(turn)
      }
      if (request.method() === 'DELETE') { deleted = true; return route.fulfill({ status: 204 }) }
      if (request.method() === 'GET' && path.endsWith('/dialogues/7')) {
        reads++
        if (reads > 1) turn.state = 'completed'
        return json(dialogue)
      }
      return json({ detail: 'Unexpected synthetic request' }, 500)
    })
    await page.goto('/test-fixtures/dialogue.html')
    await page.getByRole('combobox', { name: 'Modo', exact: true }).selectOption('guided')
    await page.getByRole('button', { name: 'Iniciar conversa' }).click()
    const input = page.getByLabel('Sua resposta em inglês')
    await input.fill('I take the bus.')
    await input.press('Tab')
    await expect(page.getByRole('button', { name: 'Enviar texto' })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByText('Resposta do roteiro · assistência indisponível')).toBeVisible()
    await expect(page.getByText('Termos usados: bus.')).toBeVisible()
    await expect(page.getByText('Termos não identificados: train.')).toBeVisible()
    await expect(input).toBeFocused()
    expect(submitted).toBe(1)
    await page.getByRole('button', { name: 'Ouvir resposta do turno 1' }).click()
    await expect.poll(() => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken)).toEqual(['Where do you go?'])
    await page.getByRole('button', { name: 'Foi útil', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Foi útil', exact: true })).toHaveAttribute('aria-pressed', 'true')
    const accessibility = await new AxeBuilder({ page }).analyze()
    expect(accessibility.violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({ path: `test-results/dialogue-${viewport.width}.png`, fullPage: true })
    await page.getByRole('button', { name: 'Excluir conversa' }).click()
    expect(deleted).toBe(false)
    await page.getByRole('button', { name: 'Confirmar exclusão' }).click()
    await expect(page.getByRole('button', { name: 'Iniciar conversa' })).toBeVisible()
    expect(deleted).toBe(true)
  })
}
