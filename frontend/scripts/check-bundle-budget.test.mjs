import assert from 'node:assert/strict'
import { randomBytes } from 'node:crypto'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, describe, it } from 'node:test'
import { checkBundleBudget, initialAssets, LIMITS } from './check-bundle-budget.mjs'

const created = []
after(() => { for (const dir of created) rmSync(dir, { recursive: true, force: true }) })

/**
 * Bytes aleatórios não comprimem: o gzip fica a poucos bytes do tamanho bruto,
 * o que permite montar um `dist` sintético com pesos conhecidos em KiB.
 * Só os nomes em `initial` entram no index.html; o resto é chunk lazy.
 */
function syntheticDist(files, initial) {
  const dir = mkdtempSync(join(tmpdir(), 'bundle-budget-'))
  created.push(dir)
  mkdirSync(join(dir, 'assets'))
  for (const [name, kib] of Object.entries(files)) {
    writeFileSync(join(dir, 'assets', name), randomBytes(kib * 1024))
  }
  const tags = initial.map((name) => name.endsWith('.css')
    ? `<link rel="stylesheet" crossorigin href="/assets/${name}">`
    : `<script type="module" crossorigin src="/assets/${name}"></script>`)
  writeFileSync(join(dir, 'index.html'),
    `<!doctype html>\n<html><head>${tags.join('\n')}</head><body><div id="root"></div></body></html>\n`)
  return dir
}

const line = (result, prefix) => result.lines.find((text) => text.includes(prefix))
const entry = ['index-abc123.js', 'index-abc123.css']

describe('orçamento do bundle com dois tetos', () => {
  it('aprova entrada e total dentro dos limites e rotula o que é inicial e o que é lazy', () => {
    const dist = syntheticDist({ 'index-abc123.js': 115, 'index-abc123.css': 10, 'lesson-study-x.js': 40 }, entry)
    const result = checkBundleBudget(dist)
    assert.equal(result.ok, true, result.lines.join('\n'))
    assert.ok(result.initial > 124 * 1024 && result.initial <= LIMITS.initial)
    assert.ok(result.total > 164 * 1024 && result.total <= LIMITS.total)
    assert.match(line(result, 'index-abc123.js'), /\(inicial\)$/)
    assert.match(line(result, 'lesson-study-x.js'), /\(lazy\)$/)
    assert.match(line(result, 'inicial (entrada'), /^OK /)
    assert.match(line(result, 'total JS/CSS'), /^OK /)
  })

  it('falha quando a entrada cresce além do teto inicial, mesmo com o total dentro do limite', () => {
    const dist = syntheticDist({ 'index-abc123.js': 125, 'index-abc123.css': 10, 'lesson-study-x.js': 40 }, entry)
    const result = checkBundleBudget(dist)
    assert.equal(result.ok, false)
    assert.ok(result.initial > LIMITS.initial)
    assert.ok(result.total <= LIMITS.total)
    assert.match(line(result, 'inicial (entrada'), /^ERRO /)
    assert.match(line(result, 'total JS/CSS'), /^OK /)
  })

  it('não falha quando um chunk lazy novo é criado dentro do teto total; o inicial não muda', () => {
    const before = checkBundleBudget(syntheticDist(
      { 'index-abc123.js': 115, 'index-abc123.css': 10, 'lesson-study-x.js': 40 }, entry))
    const after = checkBundleBudget(syntheticDist(
      { 'index-abc123.js': 115, 'index-abc123.css': 10, 'lesson-study-x.js': 40, 'assistant-y.js': 15 }, entry))
    assert.equal(after.ok, true, after.lines.join('\n'))
    assert.equal(after.initial, before.initial)
    assert.ok(after.total > before.total && after.total <= LIMITS.total)
    assert.match(line(after, 'assistant-y.js'), /\(lazy\)$/)
  })

  it('o teto total continua valendo para chunks lazy', () => {
    const result = checkBundleBudget(syntheticDist(
      { 'index-abc123.js': 115, 'index-abc123.css': 10, 'lesson-study-x.js': 40, 'assistant-y.js': 25 }, entry))
    assert.equal(result.ok, false)
    assert.ok(result.initial <= LIMITS.initial)
    assert.ok(result.total > LIMITS.total)
    assert.match(line(result, 'inicial (entrada'), /^OK /)
    assert.match(line(result, 'total JS/CSS'), /^ERRO /)
  })

  it('limites por arquivo continuam: CSS acima de 15 KiB reprova', () => {
    const result = checkBundleBudget(syntheticDist({ 'index-abc123.js': 100, 'index-abc123.css': 16 }, entry))
    assert.equal(result.ok, false)
    assert.match(line(result, 'index-abc123.css'), /^ERRO /)
  })

  it('reprova um index.html sem asset de entrada em vez de aprovar um inicial de zero bytes', () => {
    const result = checkBundleBudget(syntheticDist({ 'index-abc123.js': 10 }, []))
    assert.equal(result.ok, false)
    assert.ok(result.lines.some((text) => text.includes('não referencia nenhum asset')))
  })

  it('reconhece script, modulepreload e stylesheet do index.html gerado pelo Vite', () => {
    const html = `<script type="module" crossorigin src="/assets/index-a.js"></script>
      <link rel="modulepreload" crossorigin href="/assets/vendor-b.js">
      <link rel="stylesheet" crossorigin href="/assets/index-c.css">
      <link rel="icon" href="/icon.svg">
      <link rel="manifest" href="/manifest.webmanifest">`
    assert.deepEqual([...initialAssets(html)].sort(), ['index-a.js', 'index-c.css', 'vendor-b.js'])
  })
})

describe('reserva explícita FE-47 sem ampliar o orçamento da base', () => {
  it('aceita até 8 KiB de diálogo lazy além dos 184 KiB da base', () => {
    const result = checkBundleBudget(syntheticDist({
      'index-abc123.js': 115, 'index-abc123.css': 10, 'lesson-study-x.js': 55,
      'DialogueWorkspace-test.js': 6, 'DialogueWorkspace-test.css': 1,
    }, entry))
    assert.equal(result.ok, true, result.lines.join('\n'))
    assert.ok(result.total > LIMITS.total)
    assert.ok(result.total - result.dialogue <= LIMITS.total)
  })
  it('reprova diálogo acima da reserva mesmo quando sobra orçamento na base', () => {
    const result = checkBundleBudget(syntheticDist({
      'index-abc123.js': 100, 'index-abc123.css': 10, 'DialogueWorkspace-test.js': 9,
    }, entry))
    assert.equal(result.ok, false)
    assert.match(line(result, 'diálogo lazy'), /^ERRO /)
  })
  it('a reserva do diálogo não pode pagar crescimento dos outros módulos', () => {
    const result = checkBundleBudget(syntheticDist({
      'index-abc123.js': 115, 'index-abc123.css': 10, 'lesson-study-x.js': 60,
      'DialogueWorkspace-test.js': 1,
    }, entry))
    assert.equal(result.ok, false)
    assert.match(line(result, 'total JS/CSS base'), /^ERRO /)
  })
  it('reprova se o diálogo entrar no carregamento inicial', () => {
    const result = checkBundleBudget(syntheticDist({
      'index-abc123.js': 100, 'index-abc123.css': 10, 'DialogueWorkspace-test.js': 1,
    }, [...entry, 'DialogueWorkspace-test.js']))
    assert.equal(result.ok, false)
    assert.ok(result.lines.includes('ERRO diálogo precisa ser lazy.'))
  })
})
