import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('política de cache de mídia', () => {
  it('mantém áudio e vídeo fora do service worker', () => {
    const source = readFileSync(resolve(process.cwd(), 'public/sw.js'), 'utf8')

    expect(source).toContain("request.destination === 'audio'")
    expect(source).toContain("request.destination === 'video'")
    expect(source).toContain('Política fail-closed')
  })

  it('mantém catálogo, currículo e aula canônica disponíveis offline', () => {
    const source = readFileSync(resolve(process.cwd(), 'public/sw.js'), 'utf8')

    expect(source).toContain("url.pathname === '/api/courses'")
    expect(source).toContain('/api\\/courses\\/[^/]+\\/curriculum')
    expect(source).toContain('/api\\/courses\\/[^/]+\\/lessons\\/\\d+')
  })
})
