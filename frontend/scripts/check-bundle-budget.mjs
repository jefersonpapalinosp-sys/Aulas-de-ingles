import { gzipSync } from 'node:zlib'
import { readdirSync, readFileSync } from 'node:fs'
import { extname } from 'node:path'

const assets = readdirSync(new URL('../dist/assets', import.meta.url))
const limits = { '.js': 140 * 1024, '.css': 15 * 1024 }
const totalLimit = 170 * 1024
let total = 0
let failed = false

for (const name of assets) {
  const extension = extname(name)
  if (!(extension in limits)) continue
  const bytes = gzipSync(readFileSync(new URL(`../dist/assets/${name}`, import.meta.url))).byteLength
  total += bytes
  const ok = bytes <= limits[extension]
  console.log(`${ok ? 'OK' : 'ERRO'} ${name}: ${(bytes / 1024).toFixed(1)} KiB gzip`)
  if (!ok) failed = true
}

console.log(`${total <= totalLimit ? 'OK' : 'ERRO'} total JS/CSS: ${(total / 1024).toFixed(1)} KiB gzip`)
if (total > totalLimit) failed = true
if (failed) process.exitCode = 1
