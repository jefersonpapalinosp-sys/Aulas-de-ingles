import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Plugin, ResolvedConfig } from 'vite'

/** O worker só muda de versão quando o conteúdo efetivamente muda. */
export function pwaBuild(): Plugin {
  let config: ResolvedConfig
  return {
    name: 'aulas-pwa-release', apply: 'build', enforce: 'post',
    configResolved(value) { config = value },
    writeBundle(_, bundle) {
      const output = resolve(config.root, config.build.outDir)
      const template = readFileSync(resolve(config.publicDir, 'sw.js'), 'utf8')
      const assets = Object.keys(bundle).filter((name) => /^assets\/.+\.(js|css|woff2?|svg|png)$/.test(name)).sort()
      const entry = new Set<string>()
      function visit(name: string) {
        if (entry.has(name)) return
        entry.add(name)
        const chunk = bundle[name]
        if (chunk?.type === 'chunk') chunk.imports.forEach(visit)
      }
      Object.values(bundle).forEach((item) => {
        if (item.type === 'chunk' && item.isEntry) visit(item.fileName)
        if (item.fileName.endsWith('.css')) entry.add(item.fileName)
      })
      const html = readFileSync(resolve(output, 'index.html'))
      const hash = createHash('sha256').update(template).update(html)
      for (const name of [...assets, 'manifest.webmanifest', 'icon.svg']) {
        hash.update(name).update(readFileSync(resolve(output, name)))
      }
      const worker = template
        .replace('__AULAS_RELEASE__', hash.digest('hex').slice(0, 16))
        .replace("'__AULAS_ASSETS__'", JSON.stringify(assets.map((name) => `/${name}`)))
        .replace("'__AULAS_ENTRY__'", JSON.stringify([...entry].sort().map((name) => `/${name}`)))
        .replace('__AULAS_HTML_HASH__', createHash('sha256').update(html).digest('hex'))
      writeFileSync(resolve(output, 'sw.js'), worker)
    },
  }
}
