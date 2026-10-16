import { afterEach, expect, it, vi } from 'vitest'
import { canSyncFor } from './media'
import { setAccessToken, setSessionReadOnly, setSessionUser } from './session'

afterEach(() => { vi.restoreAllMocks(); setAccessToken(null); setSessionUser(null); setSessionReadOnly(false) })
it('envio exige rede, token, conta correspondente e perfil confirmado', () => {
  setAccessToken('test-token'); setSessionUser(7); setSessionReadOnly(false)
  expect(canSyncFor(7)).toBe(true)
  expect(canSyncFor(8)).toBe(false)
  setSessionReadOnly(true); expect(canSyncFor(7)).toBe(false)
  setSessionReadOnly(false)
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  expect(canSyncFor(7)).toBe(false)
  vi.restoreAllMocks(); setAccessToken(null)
  expect(canSyncFor(7)).toBe(false)
})
