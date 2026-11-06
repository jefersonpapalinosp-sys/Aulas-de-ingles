import { afterEach, expect, it, vi } from 'vitest'
import { scrollToTop } from './scroll'

afterEach(() => vi.unstubAllGlobals())

it.each([true, false])('respeita movimento reduzido: %s', (reduced) => {
  const scroll = vi.fn()
  vi.stubGlobal('scrollTo', scroll)
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: reduced })))
  scrollToTop()
  expect(scroll).toHaveBeenCalledWith({ top: 0, behavior: reduced ? 'instant' : 'smooth' })
})
