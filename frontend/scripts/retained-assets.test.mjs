import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, utimesSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'

const script = new URL('../40-retain-assets.sh', import.meta.url).pathname

test('retém chunks antigos, renova os atuais e expira só assets fora da janela', () => {
  const root = mkdtempSync(join(tmpdir(), 'aulas-assets-'))
  try {
    const source = join(root, 'release', 'assets')
    const archive = join(root, 'archive')
    mkdirSync(source, { recursive: true })
    mkdirSync(join(archive, 'assets'), { recursive: true })
    const old = join(archive, 'assets', 'old-hash.js')
    const expired = join(archive, 'assets', 'expired-hash.js')
    const current = join(source, 'current-hash.js')
    writeFileSync(old, 'old module')
    writeFileSync(expired, 'expired module')
    writeFileSync(current, 'current module')
    writeFileSync(join(root, 'release', 'index.html'), 'new shell')
    writeFileSync(join(root, 'release', 'sw.js'), 'new worker')
    writeFileSync(join(archive, 'unrelated.txt'), 'preserved')
    writeFileSync(join(archive, '.current-assets'), 'old-hash.js\n')
    const longAgo = new Date(Date.now() - 40 * 86400000)
    for (const file of [old, expired, current, join(archive, 'unrelated.txt')]) utimesSync(file, longAgo, longAgo)
    const result = spawnSync('sh', [script], {
      env: { ...process.env, AULAS_ASSET_SOURCE: source, AULAS_ASSET_ARCHIVE: archive }, encoding: 'utf8',
    })
    assert.equal(result.status, 0, result.stderr)
    assert.equal(readFileSync(old, 'utf8'), 'old module')
    assert.equal(readFileSync(join(archive, 'assets', 'current-hash.js'), 'utf8'), 'current module')
    assert.equal(existsSync(expired), false)
    assert.equal(existsSync(join(archive, 'index.html')), false)
    assert.equal(existsSync(join(archive, 'sw.js')), false)
    assert.equal(readFileSync(join(archive, 'unrelated.txt'), 'utf8'), 'preserved')
  } finally { rmSync(root, { recursive: true, force: true }) }
})

test('sem arquivo configurado não exige escrita no filesystem da imagem', () => {
  const result = spawnSync('sh', [script], {
    env: { ...process.env, AULAS_ASSET_ARCHIVE: '', AULAS_ASSET_SOURCE: '/nonexistent' }, encoding: 'utf8',
  })
  assert.equal(result.status, 0, result.stderr)
})

test('falha ao publicar impede o boot em vez de esconder perda de retenção', () => {
  const result = spawnSync('sh', [script], {
    env: { ...process.env, AULAS_ASSET_ARCHIVE: '/dev/null/archive' }, encoding: 'utf8',
  })
  assert.notEqual(result.status, 0)
})
