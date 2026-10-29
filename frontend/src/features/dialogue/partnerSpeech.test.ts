import { afterEach, expect, it, vi } from 'vitest'
import { PartnerSpeech } from './partnerSpeech'

afterEach(() => vi.unstubAllGlobals())
it('usa voz local en-US, respeita velocidade e ignora término após cancelamento', () => {
  const finished = vi.fn(), speak = vi.fn<(utterance: SpeechSynthesisUtterance) => void>(), cancel = vi.fn()
  const remote = { lang: 'en-US', localService: false }, local = { lang: 'en-US', localService: true }
  vi.stubGlobal('speechSynthesis', { getVoices: () => [remote, local], speak, cancel })
  vi.stubGlobal('SpeechSynthesisUtterance', class { constructor(readonly text: string) {} })
  const player = new PartnerSpeech(finished)
  expect(player.play('Hello', 0.65)).toBe(true)
  const utterance = speak.mock.calls[0]![0]
  expect(utterance.voice).toBe(local)
  expect(utterance.rate).toBe(0.65)
  player.cancel(); utterance.onend?.call(utterance, new Event('end') as SpeechSynthesisEvent)
  expect(finished).not.toHaveBeenCalled()
})
it('não transmite texto para voz remota quando falta voz local', () => {
  const speak = vi.fn<(utterance: SpeechSynthesisUtterance) => void>()
  vi.stubGlobal('speechSynthesis', { getVoices: () => [{ lang: 'en-US', localService: false }], speak, cancel: vi.fn() })
  vi.stubGlobal('SpeechSynthesisUtterance', class {})
  expect(new PartnerSpeech(vi.fn()).play('Private text', 1)).toBe(false)
  expect(speak).not.toHaveBeenCalled()
})
