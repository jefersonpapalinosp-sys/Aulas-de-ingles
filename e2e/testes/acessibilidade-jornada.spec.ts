import { expect, test } from '@playwright/test'

import AxeBuilder from '@axe-core/playwright'
import type { Locator } from '@playwright/test'
import {
  emailUnico,
  SENHA,
  LEVEL_2_SLUG,
  lessonPath,
  practicePath,
  studyPath,
  expectNoHorizontalScroll,
  ensureTrailVisible,
  tabAte,
  criarConta,
} from '../journey-helpers'

test('Sprint 25 mantém o piloto Level 2 utilizável em mobile e zoom equivalente a 200%', async ({
  page,
}) => {
  await page.setViewportSize({ width: 640, height: 360 })
  await criarConta(page, 'Reflow Level 2 Sprint 25')
  await page.goto(lessonPath(1, LEVEL_2_SLUG))

  await expect(page.getByRole('heading', { level: 1, name: 'Budget Cuts' })).toBeVisible()
  await expectNoHorizontalScroll(page)
  const openTrail = page.getByRole('button', { name: /Abrir trilha de aulas/ })
  await expect(openTrail).toContainText('Level 2 · Aula 1 · Budget Cuts')
  await tabAte(page, openTrail)
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('combobox', { name: 'Curso' })).toHaveValue(LEVEL_2_SLUG)
  await expect(
    dialog.getByRole('heading', { name: "Let's Learn English — Level 2" }),
  ).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(openTrail).toBeFocused()

  const accessibility = await new AxeBuilder({ page })
    .include('#main-content')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(accessibility.violations).toEqual([])
})

test('rota canônica mantém aula ativa e navegação completa por teclado', async ({ page }) => {
  await criarConta(page, 'Navegação E2E')
  await page.goto(lessonPath(31))

  await expect(page).toHaveURL(new RegExp(`${lessonPath(31)}$`))
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
  const dialog = await ensureTrailVisible(page)
  const navigation = dialog ?? page.getByRole('complementary', { name: 'Navegação do curso' })
  const activeLesson = navigation.getByRole('link', {
    name: /31.*Take Me Out to the Ball Game/,
  })
  await expect(activeLesson).toHaveAttribute('aria-current', 'page')

  const shortcuts = navigation.getByRole('navigation', { name: 'Atalhos' })
  for (const name of ['Hoje', 'Cursos', 'Listening rápido', 'Revisar', 'Caderno', 'Meus dados', 'Avaliação']) {
    await expect(shortcuts.getByRole('link', { name: new RegExp(`^${name}`) })).toBeVisible()
  }
  expect(
    await shortcuts.evaluate(
      (navigation) => {
        const unitButton = navigation
          .closest('.trail-panel')
          ?.querySelector('button[aria-controls*="-trail-unit-"]')
        return (
          unitButton !== null &&
          Boolean(
            navigation.compareDocumentPosition(unitButton) & Node.DOCUMENT_POSITION_FOLLOWING,
          )
        )
      },
    ),
  ).toBeTruthy()

  const courseSelector = navigation.getByRole('combobox', { name: 'Curso' })
  await courseSelector.focus()
  for (const name of ['Hoje', 'Cursos', 'Listening rápido', 'Revisar', 'Caderno', 'Meus dados', 'Avaliação', 'Mapa da unidade']) {
    await page.keyboard.press('Tab')
    await expect(shortcuts.getByRole('link', { name: new RegExp(`^${name}`) })).toBeFocused()
  }
  await page.keyboard.press('Tab')
  const search = navigation.getByRole('searchbox', { name: 'Buscar aula' })
  await expect(search).toBeFocused()
  await page.keyboard.type('The Woods Are Alive')
  const lesson40 = navigation.getByRole('link', { name: /40.*The Woods Are Alive/ })
  await tabAte(page, lesson40, 10)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`${lessonPath(40)}$`))
  await expect(page.getByRole('heading', { name: 'The Woods Are Alive' })).toBeVisible()
})

test('drawer da trilha preserva foco e reflow nos viewports críticos', async ({ page }) => {
  await criarConta(page, 'Drawer E2E')
  const viewports = [
    { name: '320 px', width: 320, height: 640 },
    { name: '360 px', width: 360, height: 740 },
    { name: '768 px', width: 768, height: 1024 },
    { name: 'zoom equivalente a 200%', width: 640, height: 360 },
  ]

  for (const viewport of viewports) {
    await test.step(viewport.name, async () => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(lessonPath(31))
      await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
      await expectNoHorizontalScroll(page)

      const openDrawer = page.getByRole('button', { name: /Abrir trilha de aulas/ })
      await expect(openDrawer).toHaveAttribute('aria-expanded', 'false')
      await openDrawer.focus()
      await page.keyboard.press('Enter')

      const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
      await expect(dialog).toBeVisible()
      await expect(openDrawer).toHaveAttribute('aria-expanded', 'true')
      await expect(dialog.getByRole('searchbox', { name: 'Buscar aula' })).toBeFocused()
      await expectNoHorizontalScroll(page)

      for (let index = 0; index < 24; index += 1) {
        await page.keyboard.press('Tab')
        expect(
          await dialog.evaluate((element) => element.contains(document.activeElement)),
        ).toBeTruthy()
      }

      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(openDrawer).toHaveAttribute('aria-expanded', 'false')
      await expect(openDrawer).toBeFocused()
      await expectNoHorizontalScroll(page)
    })
  }
})

test('cadastro permanece acessível em viewport equivalente a zoom de 200%', async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 360 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Ainda não tenho conta' }).click()

  const caixa = page.locator('.login-caixa')
  const nome = page.getByLabel('Nome')
  await expect(caixa).toBeVisible()
  await expect(nome).toBeVisible()
  await expect(nome).toBeFocused()

  expect(await nome.evaluate((element) => element.getBoundingClientRect().height)).toBeLessThan(60)
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
  expect(await caixa.evaluate((element) => element.getBoundingClientRect().top)).toBeGreaterThanOrEqual(0)
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
  ).toBeTruthy()
})

test('cadastro e salto ao conteúdo funcionam com teclado real do navegador', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByLabel('E-mail')).toBeVisible()

  await page.keyboard.press('Tab')
  await expect(page.getByLabel('E-mail')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('Senha')).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByLabel('E-mail')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByLabel('E-mail')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('Senha')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Ainda não tenho conta' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Nome')).toBeFocused()

  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Já tenho conta' })).toBeFocused()
  await page.keyboard.press('Space')
  await expect(page.getByRole('button', { name: 'Ainda não tenho conta' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Nome')).toBeFocused()

  await page.keyboard.type('Teclado E2E')
  await page.keyboard.press('Tab')
  await page.keyboard.type(emailUnico())
  await page.keyboard.press('Tab')
  await page.keyboard.type(SENHA)
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Criar conta' })).toBeFocused()
  await page.keyboard.press('Enter')

  await expect(page).toHaveURL(/\/inicio$/)
  await expect(page.getByRole('heading', { name: 'Hoje' })).toBeVisible()
  await expect(page.locator('#main-content')).toBeFocused()
  const skipLink = page.getByRole('link', { name: 'Pular para o conteúdo' })
  for (let tentativa = 0; tentativa < 100; tentativa += 1) {
    if (await skipLink.evaluate((element) => element === document.activeElement)) break
    await page.keyboard.press('Shift+Tab')
  }
  await expect(skipLink).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()

  await page.goto(lessonPath(31))
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()

  const comecar = page.getByRole('link', { name: 'Começar estudo' })
  await tabAte(page, comecar)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`${studyPath(31, 'preparar')}$`))

  const avancar = page.getByRole('button', { name: 'Concluir e ir para Assistir' })
  await tabAte(page, avancar)
  await page.keyboard.press('Space')
  await expect(page).toHaveURL(new RegExp(`${studyPath(31, 'assistir')}$`))
  await expect(page.getByRole('heading', { name: 'Escute primeiro pelo contexto' })).toBeVisible()

  await page.goto(practicePath(31))
  await expect(page.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeVisible()
  const iniciarPratica = page.getByRole('button', { name: 'Começar Prática guiada' })
  await tabAte(page, iniciarPratica)
  await page.keyboard.press('Enter')
  await expect(page.locator('.practice-question')).toBeVisible()
  const resposta = page.getByLabel('Resposta do exercício 1')
  await tabAte(page, resposta)
  await page.keyboard.type('faster')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Verificar' }).first()).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByText('Correto').first()).toBeVisible()

  const compactOpen = page.getByRole('button', { name: /Abrir trilha de aulas/ })
  let caderno: Locator
  if (await compactOpen.isVisible()) {
    await tabAte(page, compactOpen)
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
    await expect(dialog).toBeVisible()
    caderno = dialog.getByRole('link', { name: 'Caderno' })
  } else {
    caderno = page.getByRole('link', { name: 'Caderno' })
  }
  await tabAte(page, caderno)
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Caderno de inglês' })).toBeVisible()

  const anotacao = page.getByRole('textbox', { name: 'Conteúdo', exact: true })
  await tabAte(page, anotacao)
  await page.keyboard.type('Comparatives use than.')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Salvar no caderno' })).toBeFocused()
  await page.keyboard.press('Space')
  await expect(page.locator('.notebook-message[role="status"]')).toHaveText(
    'Anotação salva no seu caderno.',
  )

  let revisar: Locator
  if (await compactOpen.isVisible()) {
    await tabAte(page, compactOpen)
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
    await expect(dialog).toBeVisible()
    revisar = dialog.getByRole('link', { name: /^Revisar/ })
  } else {
    revisar = page.getByRole('link', { name: /^Revisar/ })
  }
  await tabAte(page, revisar)
  await page.keyboard.press('Enter')
  await expect(
    page.getByRole('heading', { name: /Revisar|Nada para revisar agora|Nenhum item/ }),
  ).toBeVisible()

  const tipo = page.getByLabel('Tipo')
  await tabAte(page, tipo)
  await page.keyboard.press('v')
  await expect(tipo).toHaveValue('vocabulary')
})

test('login e cadastro preservam controles em contraste forçado', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' })
  await page.goto('/')

  expect(await page.evaluate(() => matchMedia('(forced-colors: active)').matches)).toBeTruthy()
  await expect(page.getByLabel('E-mail')).toBeVisible()
  await expect(page.getByLabel('Senha')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()

  await page.keyboard.press('Tab')
  await expect(page.getByLabel('E-mail')).toBeFocused()
  expect(
    await page.getByLabel('E-mail').evaluate((element) => getComputedStyle(element).outlineStyle),
  ).not.toBe('none')

  await page.getByRole('button', { name: 'Ainda não tenho conta' }).click()
  await expect(page.getByLabel('Nome')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Criar conta' })).toBeVisible()

  const resultado = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(
    resultado.violations.filter(
      ({ impact }) => impact === 'serious' || impact === 'critical',
    ),
  ).toEqual([])

  await criarConta(page, 'Contraste E2E')
  for (const rota of [
    '/',
    lessonPath(31),
    studyPath(40, 'assistir'),
    '/revisar',
    '/caderno',
  ]) {
    await page.goto(rota)
    await expect(page.locator('#main-content')).toBeVisible()
    const pagina = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze()
    expect(
      pagina.violations.filter(
        ({ impact }) => impact === 'serious' || impact === 'critical',
      ),
    ).toEqual([])
  }
})

test('painel e aula não têm violações WCAG sérias ou críticas', async ({ page }) => {
  await criarConta(page, 'Acessibilidade E2E')

  const painel = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(painel.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical'))
    .toEqual([])

  await page.goto(lessonPath(40))
  await expect(page.getByRole('heading', { name: 'The Woods Are Alive' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Começar estudo' })).toHaveAttribute(
    'href',
    studyPath(40),
  )
  await page.goto(studyPath(40, 'assistir'))
  await expect(page.getByRole('heading', { name: 'Conversa da Aula 40' })).toBeVisible()
  await expect(page.getByText('What part does the director give Anna?')).toBeVisible()
  const aula = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(aula.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical'))
    .toEqual([])
})
