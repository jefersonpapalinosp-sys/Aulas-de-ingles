import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VoiceRecorder } from './voiceRecorder'
import { clearVoiceDraft, retainVoiceDraft, takeVoiceDraft } from './voiceDraft'

class Recorder {
  static isTypeSupported = vi.fn(() => true)
  static latest: Recorder
  state = 'inactive'
  mimeType: string
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(_stream: MediaStream, options: MediaRecorderOptions) {
    this.mimeType = options.mimeType!
    Recorder.latest = this
  }
  start() { this.state = 'recording' }
  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['voice']) })
    this.onstop?.()
  }
}
const callbacks = () => ({ started: vi.fn(), finished: vi.fn(), failed: vi.fn() })
function permission() {
  const stop = vi.fn()
  const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream
  let resolve!: (stream: MediaStream) => void
  const getUserMedia = vi.fn(() => new Promise<MediaStream>((done) => { resolve = done }))
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
  return { stop, stream, resolve: () => resolve(stream) }
}
beforeEach(() => {
  vi.useFakeTimers()
  Recorder.isTypeSupported.mockReturnValue(true)
  vi.stubGlobal('MediaRecorder', Recorder)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); clearVoiceDraft('own') })

describe('VoiceRecorder lifecycle', () => {
  it('encerra permissão tardia sem iniciar gravação ou timer após cancelamento/saída', async () => {
    const mic = permission(), events = callbacks(), controller = new VoiceRecorder(events)
    const pending = controller.start(30_000, ['audio/webm'])
    controller.cancel()
    mic.resolve(); await pending
    expect(mic.stop).toHaveBeenCalledOnce()
    expect(events.started).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('limpa tracks e timers ao cancelar gravação ativa, sem entregar blob de outra rota', async () => {
    const mic = permission(), events = callbacks(), controller = new VoiceRecorder(events)
    const pending = controller.start(30_000, ['audio/webm']); mic.resolve(); await pending
    controller.cancel(); controller.cancel()
    expect(mic.stop).toHaveBeenCalledOnce()
    expect(events.finished).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('para no limite e libera o microfone antes de oferecer blob', async () => {
    const mic = permission(), events = callbacks(), controller = new VoiceRecorder(events)
    const pending = controller.start(30_000, ['audio/webm']); mic.resolve(); await pending
    await vi.advanceTimersByTimeAsync(30_000)
    expect(mic.stop).toHaveBeenCalledOnce()
    expect(events.finished).toHaveBeenCalledWith(expect.any(Blob), 30_000)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('prefere MP4 quando WebM não é suportado (capacidade, não detecção de navegador)', async () => {
    Recorder.isTypeSupported.mockImplementation((type?: string) => type === 'audio/mp4')
    const mic = permission(), events = callbacks(), controller = new VoiceRecorder(events)
    const pending = controller.start(30_000, ['audio/webm', 'audio/mp4']); mic.resolve(); await pending
    controller.stop()
    expect((events.finished.mock.calls[0]![0] as Blob).type).toBe('audio/mp4')
  })
  it('não solicita microfone sem formato compatível e explica a alternativa', async () => {
    Recorder.isTypeSupported.mockReturnValue(false)
    const mic = permission(), events = callbacks()
    await new VoiceRecorder(events).start(30_000, ['audio/webm'])
    expect(events.failed).toHaveBeenCalledWith(expect.stringMatching(/pratique em voz alta/))
    expect(mic.stop).not.toHaveBeenCalled()
  })
  it('libera tracks quando construtor/start ou onerror falham', async () => {
    const mic = permission(), events = callbacks(), controller = new VoiceRecorder(events)
    const pending = controller.start(30_000, ['audio/webm']); mic.resolve(); await pending
    Recorder.latest.onerror?.()
    expect(mic.stop).toHaveBeenCalledOnce()
    expect(events.finished).not.toHaveBeenCalled()
    expect(events.failed).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
    vi.spyOn(Recorder.prototype, 'start').mockImplementation(() => { throw new Error('start failed') })
    const mic2 = permission()
    const next = controller.start(30_000, ['audio/webm']); mic2.resolve(); await next
    expect(mic2.stop).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('recuperação transitória após expiração', () => {
  const value = { key: 'own', blob: new Blob(['voice']), duration: 1000, attemptId: 44 }
  it('só a mesma conta/contexto recupera, uma vez', () => {
    retainVoiceDraft(value)
    expect(takeVoiceDraft('own')).toEqual(value)
    expect(takeVoiceDraft('own')).toBeNull()
    retainVoiceDraft(value)
    expect(takeVoiceDraft('other')).toBeNull()
    expect(takeVoiceDraft('own')).toBeNull()
  })
  it('expira a referência em cinco minutos sem armazenamento persistente', () => {
    retainVoiceDraft(value)
    vi.advanceTimersByTime(300_000)
    expect(takeVoiceDraft('own')).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })
})
