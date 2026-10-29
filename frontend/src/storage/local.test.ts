import { afterEach, describe, expect, it, vi } from 'vitest'
import { readLocal, removeLocal, writeLocal } from './local'

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

describe('acesso local explícito', () => {
  it('distingue ausência, texto vazio, sucesso e remoção', () => {
    expect(readLocal('draft')).toEqual({ ok: true, value: null })
    expect(writeLocal('draft', '').ok).toBe(true)
    expect(readLocal('draft')).toEqual({ ok: true, value: '' })
    expect(removeLocal('draft').ok).toBe(true)
    expect(readLocal('draft')).toEqual({ ok: true, value: null })
  })
  it('getter bloqueado não derruba a tela nem é tratado como chave ausente', () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => { throw new DOMException('', 'SecurityError') })
    expect(readLocal('draft')).toMatchObject({ ok: false })
    expect(writeLocal('draft', 'privado')).toMatchObject({ ok: false })
    expect(removeLocal('draft')).toMatchObject({ ok: false })
  })
  it('quota não simula sucesso, não altera a cópia anterior e não expõe texto no erro', () => {
    localStorage.setItem('draft', 'cópia anterior')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('texto privado', 'QuotaExceededError') })
    expect(writeLocal('draft', 'novo texto')).toEqual({ ok: false, error: expect.stringContaining('cheio') as unknown })
    expect(localStorage.getItem('draft')).toBe('cópia anterior')
  })
})
