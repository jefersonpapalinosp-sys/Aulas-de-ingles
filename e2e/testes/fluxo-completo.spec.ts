import { expect, test } from '@playwright/test'

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

test('sem sessão, a aplicação pede login', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()
  // Rota interna também cai no login.
  await page.goto('/revisar')
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()
})
