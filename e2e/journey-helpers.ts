import { expect, type Page, type Locator } from '@playwright/test'

export function emailUnico() {
  return `e2e-${Date.now()}-${Math.floor(Math.random() * 1000)}@exemplo.com`
}

export const SENHA = 'senha-bem-grande'

/** Títulos como "Find Your Joy!" e "Flour Baby, Part 1" têm caracteres de regex. */
export function escapeRegex(texto: string): string {
  return texto.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export const LEVEL_1_SLUG = 'voa-level-1'

export const LEVEL_2_SLUG = 'voa-level-2'

export function coursePath(courseSlug: string): string {
  return `/cursos/${courseSlug}`
}

export function courseCompletionPath(courseSlug = LEVEL_1_SLUG): string {
  return `${coursePath(courseSlug)}/conclusao`
}

export function lessonPath(lessonNumber: number, courseSlug = LEVEL_1_SLUG): string {
  return `${coursePath(courseSlug)}/aulas/${lessonNumber}`
}

export function practicePath(lessonNumber: number, courseSlug = LEVEL_1_SLUG): string {
  return `${lessonPath(lessonNumber, courseSlug)}/exercicios`
}

export function courseReviewPath(unitSlug: string, courseSlug = LEVEL_1_SLUG): string {
  return `${coursePath(courseSlug)}/unidades/${unitSlug}/checkpoint`
}

export function unitPath(unitSlug: string, courseSlug = LEVEL_1_SLUG): string {
  return `${coursePath(courseSlug)}/unidades/${unitSlug}`
}

export function assessmentPath(unitSlug: string, courseSlug = LEVEL_1_SLUG): string {
  return `${unitPath(unitSlug, courseSlug)}/avaliacao`
}

export function studyPath(
  lessonNumber: number,
  step?: 'preparar' | 'assistir' | 'estudar' | 'praticar' | 'revisar',
  courseSlug = LEVEL_1_SLUG,
): string {
  const base = `${lessonPath(lessonNumber, courseSlug)}/estudar`
  return step ? `${base}/${step}` : base
}

export type QueueSnapshot = {
  version: number
  attempts: Array<{
    userId: number
    exerciseId: number
    answer: string
    idempotencyKey: string
    sessionId?: number
    courseSlug?: string
    lessonNumber?: number
  }>
  receipts: Array<{ userId: number; idempotencyKey: string }>
}

export async function readAttemptQueue(page: Page): Promise<QueueSnapshot> {
  return page.evaluate(() => new Promise<QueueSnapshot>((resolve, reject) => {
    const opened = indexedDB.open('aulas:offline-attempts:v3', 1)
    // Uma fila ausente deve falhar, não ser criada pelo próprio teste.
    opened.onupgradeneeded = () => opened.transaction?.abort()
    opened.onerror = () => reject(opened.error)
    opened.onsuccess = () => {
      const db = opened.result
      const tx = db.transaction(['attempts', 'receipts'], 'readonly')
      const attempts = tx.objectStore('attempts').getAll()
      const receipts = tx.objectStore('receipts').getAll()
      tx.oncomplete = () => {
        db.close()
        resolve({ version: db.version, attempts: attempts.result, receipts: receipts.result })
      }
      tx.onabort = () => { db.close(); reject(tx.error) }
    }
  }))
}

export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBeTruthy()
}

export async function ensureTrailVisible(page: Page): Promise<Locator | null> {
  const openDrawer = page.getByRole('button', { name: /Abrir trilha de aulas/ })
  const desktopShortcuts = page.getByRole('navigation', { name: 'Atalhos', exact: true })
  // Após reload, o React pode ainda não ter montado o shell. `isVisible()` não
  // espera e fazia o helper concluir incorretamente que estava no desktop.
  await expect
    .poll(async () => (await openDrawer.isVisible()) || (await desktopShortcuts.isVisible()))
    .toBe(true)
  if (!(await openDrawer.isVisible())) return null
  if ((await openDrawer.getAttribute('aria-expanded')) !== 'true') await openDrawer.click()
  const dialog = page.getByRole('dialog', { name: 'Trilha de estudo' })
  await expect(dialog).toBeVisible()
  return dialog
}

export async function globalLink(page: Page, name: RegExp): Promise<Locator> {
  const dialog = await ensureTrailVisible(page)
  const scope = dialog ?? page.getByRole('navigation', { name: 'Atalhos', exact: true })
  return scope.getByRole('link', { name })
}

export async function expectCourseProgress(page: Page, completed: number): Promise<void> {
  const dialog = await ensureTrailVisible(page)
  const scope = dialog ?? page
  await expect(
    scope.getByRole('progressbar', { name: 'Progresso das aulas do curso' }),
  ).toHaveAttribute('aria-valuenow', String(completed))
}

export async function tabAte(page: Page, alvo: Locator, limite = 80): Promise<void> {
  await expect(alvo).toBeVisible()
  for (let tentativa = 0; tentativa < limite; tentativa += 1) {
    await page.keyboard.press('Tab')
    if (await alvo.evaluate((element) => element === document.activeElement)) return
  }
  throw new Error(`O foco não alcançou o controle após ${limite} acionamentos de Tab.`)
}

/** Cria a conta e espera a aplicação terminar a transição pós-login.
 *  Navegar antes disso cai de volta na tela de entrada. */
export async function criarConta(page: Page, nome: string): Promise<string> {
  const email = emailUnico()
  await page.goto('/')
  await page.getByRole('button', { name: 'Ainda não tenho conta' }).click()
  await page.getByLabel('Nome').fill(nome)
  await page.getByLabel('E-mail').fill(email)
  await page.getByLabel('Senha').fill(SENHA)
  const registered = page.waitForResponse((response) =>
    response.url().endsWith('/api/auth/register') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Criar conta' }).click()
  // Aguarda o contrato HTTP antes de medir a transição da UI; mantém timeout global.
  expect((await registered).status()).toBe(201)
  await expect(page).toHaveURL(/\/inicio$/)
  await expect(page.getByRole('heading', { name: 'Hoje' })).toBeVisible()
  return email
}

export type PracticeSessionE2E = {
  items: Array<{ exercise: { prompt: string } }>
}

export async function iniciarPraticaGuiada(
  page: Page,
  lessonNumber: number,
  courseSlug = LEVEL_1_SLUG,
): Promise<PracticeSessionE2E> {
  const sessaoCriada = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        `/api/courses/${courseSlug}/lessons/${lessonNumber}/practice-sessions` &&
      response.request().method() === 'POST' &&
      response.ok(),
  )
  const iniciar = page.getByRole('button', { name: 'Começar Prática guiada' })
  await expect(iniciar).toBeEnabled()
  await iniciar.click()
  const sessao = (await (await sessaoCriada).json()) as PracticeSessionE2E
  await expect(page.locator('.practice-question')).toBeVisible()
  return sessao
}

export async function avancarAteEnunciado(
  page: Page,
  sessao: PracticeSessionE2E,
  enunciado: RegExp,
): Promise<Locator> {
  const indice = sessao.items.findIndex((item) => enunciado.test(item.exercise.prompt))
  if (indice < 0) throw new Error(`A sessão não contém o exercício ${enunciado}.`)

  for (let atual = 0; atual < indice; atual += 1) {
    const questao = page.locator('.practice-question')
    await questao.getByRole('button', { name: 'Resposta' }).click()
    await expect(questao.locator('[id$="-verdict"]').getByText('Resposta', { exact: true })).toBeVisible()
    const proxima = page
      .getByRole('navigation', { name: 'Questões da sessão' })
      .getByRole('button', { name: 'Próxima →' })
    await expect(proxima).toBeEnabled()
    await proxima.click()
    await expect(page.locator('.practice-runner-head')).toContainText(
      `Questão ${atual + 2} de`,
    )
  }

  const questao = page.locator('.practice-question')
  await expect(questao.getByRole('heading', { level: 3 })).toContainText(enunciado)
  return questao
}
