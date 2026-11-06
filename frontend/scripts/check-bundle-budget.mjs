/**
 * Orçamento do bundle em dois tetos independentes, medidos em gzip:
 *
 * - INICIAL ≤ 132 KiB: o que o navegador baixa antes da primeira tela — o chunk
 *   de entrada, qualquer `modulepreload` e o CSS referenciados por
 *   dist/index.html. FE-44 mediu ~126,6 KiB.
 * - BASE ≤ 184 KiB: JS/CSS anteriores ao FE-47, incluindo os chunks
 *   lazy (lesson-study, study-tools, …). FE-44 mediu ~176,5 KiB.
 *
 * DIÁLOGO ≤ 8 KiB: JS/CSS do DialogueWorkspace, sempre lazy (FE-47).
 * LISTENING ≤ 3 KiB: catálogo externo lazy, acrescentado na Sprint 59.
 * LISTENING NATIVO ≤ 13 KiB: piloto, histórico, fila, player e sincronizador
 * de posição compartilhado com VOA, todos lazy (Sprints 60–61).
 * O conjunto base + diálogo + listening + nativo fica limitado a 208 KiB.
 * Um chunk lazy novo conta só no total; o teto inicial não o penaliza. Os
 * limites por arquivo (JS 140 KiB, CSS 15 KiB) seguem iguais aos de FE-40.
 *
 * O módulo exporta `checkBundleBudget(distDir)` para o teste em
 * check-bundle-budget.test.mjs e só imprime/define exit code quando executado
 * diretamente (`npm run check:budget`).
 */
import { readdirSync, readFileSync } from 'node:fs'
import { extname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { gzipSync } from 'node:zlib'

export const LIMITS = Object.freeze({
  initial: 132 * 1024,
  total: 184 * 1024,
  dialogue: 8 * 1024,
  listening: 3 * 1024,
  nativeListening: 13 * 1024,
  file: Object.freeze({ '.js': 140 * 1024, '.css': 15 * 1024 }),
})

const kib = (bytes) => `${(bytes / 1024).toFixed(1)} KiB gzip`

/** Nomes dos assets que o index.html carrega de saída: entrada, modulepreload e CSS. */
export function initialAssets(html) {
  const names = new Set()
  const tags = html.matchAll(/<(script|link)\b[^>]*?\b(?:src|href)="(?:\.?\/)?assets\/([^"]+)"[^>]*>/g)
  for (const [tag, kind, name] of tags) {
    if (kind === 'script' || /\brel="(?:stylesheet|modulepreload)"/.test(tag)) names.add(name)
  }
  return names
}

export function checkBundleBudget(distDir, limits = LIMITS) {
  const lines = []
  const initialNames = initialAssets(readFileSync(join(distDir, 'index.html'), 'utf8'))
  let initial = 0
  let total = 0
  let dialogue = 0
  let listening = 0
  let nativeListening = 0
  let failed = false

  for (const name of readdirSync(join(distDir, 'assets')).sort()) {
    const extension = extname(name)
    if (!(extension in limits.file)) continue
    const bytes = gzipSync(readFileSync(join(distDir, 'assets', name))).byteLength
    const isInitial = initialNames.has(name)
    total += bytes
    if (/^DialogueWorkspace-[\w-]+\.(js|css)$/.test(name)) {
      dialogue += bytes
      if (isInitial) { failed = true; lines.push('ERRO diálogo precisa ser lazy.') }
    }
    if (isInitial) initial += bytes
    if (/^ListeningPage-[\w-]+\.(js|css)$/.test(name)) {
      listening += bytes
      if (isInitial) { failed = true; lines.push('ERRO listening precisa ser lazy.') }
    }
    if (/^(native-listening|native-store|position-sync|audio-controls)-[\w-]+\.(js|css)$/.test(name)
      || /^listening-[\w-]+\.css$/.test(name)) {
      nativeListening += bytes
      if (isInitial) { failed = true; lines.push('ERRO listening nativo precisa ser lazy.') }
    }
    const ok = bytes <= limits.file[extension]
    if (!ok) failed = true
    lines.push(`${ok ? 'OK' : 'ERRO'} ${name}: ${kib(bytes)} (${isInitial ? 'inicial' : 'lazy'})`)
  }

  if (initialNames.size === 0) {
    failed = true
    lines.push('ERRO index.html não referencia nenhum asset de entrada.')
  }
  const initialOk = initial <= limits.initial
  const totalOk = total - dialogue - listening - nativeListening <= limits.total
  const dialogueOk = dialogue <= limits.dialogue
  const listeningLimit = limits.listening ?? LIMITS.listening
  const nativeLimit = limits.nativeListening ?? LIMITS.nativeListening
  const nativeOk = nativeListening <= nativeLimit
  const listeningOk = listening <= listeningLimit
  lines.push(`${initialOk ? 'OK' : 'ERRO'} inicial (entrada + CSS do index.html): ${kib(initial)} de ${kib(limits.initial)}`)
  lines.push(`${totalOk ? 'OK' : 'ERRO'} total JS/CSS base: ${kib(total - dialogue - listening - nativeListening)} de ${kib(limits.total)}`)

  lines.push(`${dialogueOk ? 'OK' : 'ERRO'} diálogo lazy: ${kib(dialogue)} de ${kib(limits.dialogue)}`)
  lines.push(`${listeningOk ? 'OK' : 'ERRO'} listening lazy: ${kib(listening)} de ${kib(listeningLimit)}`)
  lines.push(`Base: ${kib(total - dialogue - listening - nativeListening)}; conjunto: ${kib(total)} de ${kib(limits.total + limits.dialogue + listeningLimit + nativeLimit)}`)
  lines.push(`${nativeOk ? 'OK' : 'ERRO'} listening nativo lazy: ${kib(nativeListening)} de ${kib(nativeLimit)}`)
  return { ok: !failed && initialOk && totalOk && dialogueOk && listeningOk && nativeOk, initial, total, dialogue, listening, nativeListening, lines }
}

const invokedDirectly = Boolean(process.argv[1])
  && import.meta.url === pathToFileURL(resolve(process.argv[1])).href

if (invokedDirectly) {
  const result = checkBundleBudget(fileURLToPath(new URL('../dist', import.meta.url)))
  console.log(result.lines.join('\n'))
  if (!result.ok) process.exitCode = 1
}
