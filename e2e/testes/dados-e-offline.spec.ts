import { expect, test } from '@playwright/test'
import { silentWav } from '../audio-fixture'

import {
  emailUnico,
  SENHA,
  LEVEL_1_SLUG,
  lessonPath,
  practicePath,
  globalLink,
  criarConta,
  iniciarPraticaGuiada,
} from '../journey-helpers'

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
  const lesson = await (
    await request.get(`/api/courses/${LEVEL_1_SLUG}/lessons/31`)
  ).json()
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
    headers: { ...headers, 'Content-Type': 'audio/wav' },
    data: silentWav(),
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
  await (await globalLink(page, /^Caderno$/)).click()
  await expect(page.getByRole('heading', { name: 'Caderno de inglês' })).toBeVisible()
  await expect(page.getByText(/As anotações são privadas e não alteram as aulas/)).toBeVisible()

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
  await expect(page.getByRole('heading', { name: 'Começar a Aula 1' })).toBeVisible()
  await expect(page.getByText(/próxima aula ainda não concluída/)).toBeVisible()
  const grammarBefore = page.locator('.today-skills li').filter({ hasText: 'Gramática' })
  await expect(grammarBefore.getByText('Dados insuficientes (0/3)')).toBeVisible()

  await page.getByRole('textbox', { name: 'Meta', exact: true }).fill('Inglês para uma viagem')
  await page.getByLabel('Minutos por semana').fill('120')
  await page.getByText('Qua', { exact: true }).click()
  await page.getByText('Sáb', { exact: true }).click()
  await page.getByRole('button', { name: 'Salvar plano' }).click()
  await expect(page.locator('.today-save[role="status"]')).toHaveText('Plano salvo.')
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Meta', exact: true })).toHaveValue(
    'Inglês para uma viagem',
  )
  await expect(page.getByLabel('Minutos por semana')).toHaveValue('120')

  await page.goto(practicePath(31))
  await iniciarPraticaGuiada(page, 31)
  const exercise = page.locator('.practice-question')
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
  await page.goto(practicePath(31))

  await iniciarPraticaGuiada(page, 31)
  const exercise = page.locator('.practice-question')
  await exercise.getByRole('textbox').fill('more fast')
  await exercise.getByRole('button', { name: 'Verificar' }).click()
  await expect(exercise.getByText('Ainda não')).toBeVisible()

  await (await globalLink(page, /^Revisar/)).click()
  await expect(page.getByRole('heading', { name: 'Revisar' })).toBeVisible()
  await expect(page.getByText('Por que voltou?')).toBeVisible()
  await expect(page.getByText(/resposta incorreta/)).toBeVisible()
  await page.getByLabel('Tipo').selectOption('grammar_error')
  await page.getByLabel('Competência').selectOption('grammar')
  await page.getByLabel('Duração').selectOption('2')
  await expect(page.locator('.review-card-meta')).toContainText('Erro gramatical')

  await page.getByRole('button', { name: 'Suspender item' }).click()
  await expect(page.locator('.ultima[role="status"]')).toContainText('Item suspenso')
  await expect(page.getByRole('heading', { name: 'Nenhum item com estes filtros' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Itens suspensos' })).toBeVisible()

  await page.getByRole('button', { name: 'Reativar' }).click()
  await expect(page.getByRole('button', { name: 'Suspender item' })).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Excluir item' }).click()
  await expect(page.locator('.ultima[role="status"]')).toContainText('Item excluído')
  await expect(page.getByRole('heading', { name: 'Nenhum item com estes filtros' })).toBeVisible()
})

test('PWA mantém a aula pública disponível offline', async ({ page, context }) => {
  await criarConta(page, 'Offline E2E')
  await page.goto(lessonPath(31))
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()

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
  try {
    await page.reload()
    await expect(page.getByText(/Você está offline/)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Abrir laboratório' })).toHaveAttribute(
      'href',
      practicePath(31),
    )
  } finally {
    await context.setOffline(false)
  }
})
