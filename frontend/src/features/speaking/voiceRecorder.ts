/** Uma requisição de permissão não é cancelável: a geração invalida respostas tardias. */
export const recordingTypes = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus']

export class VoiceRecorder {
  private generation = 0
  private recorder: MediaRecorder | null = null
  private stream: MediaStream | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private started = 0
  private duration = 0

  constructor(private callbacks: {
    started: () => void
    finished: (blob: Blob, duration: number) => void
    failed: (message: string) => void
  }) {}

  private release() {
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
  }

  cancel() {
    this.generation++
    const recorder = this.recorder
    this.recorder = null
    if (recorder) {
      recorder.ondataavailable = null
      recorder.onstop = null
      recorder.onerror = null
      try { if (recorder.state !== 'inactive') recorder.stop() } catch { /* Tracks ainda precisam parar. */ }
      finally { this.release() }
    } else this.release()
  }

  stop() {
    this.duration = Math.max(1, Math.round(performance.now() - this.started))
    try { if (this.recorder?.state === 'recording') this.recorder.stop() }
    catch {
      this.cancel()
      this.callbacks.failed('Não foi possível finalizar a gravação. Tente novamente.')
    } finally { this.release() }
  }

  async start(maxDuration: number, mimeTypes: string[]) {
    this.cancel()
    const generation = this.generation
    const current = () => this.generation === generation
    try {
      const mimeType = recordingTypes.find((type) =>
        mimeTypes.includes(type.split(';')[0]!) && MediaRecorder.isTypeSupported(type))
      if (!mimeType) throw new Error('Nenhum formato de gravação compatível. Ouça o modelo e pratique em voz alta.')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return }
      this.stream = stream
      const recorder = new MediaRecorder(stream, { mimeType })
      this.recorder = recorder
      const chunks: Blob[] = []
      recorder.ondataavailable = (event) => {
        if (current() && event.data.size > 0) chunks.push(event.data)
      }
      recorder.onstop = () => {
        if (!current()) return
        const duration = this.duration || Math.max(1, Math.round(performance.now() - this.started))
        this.release()
        this.recorder = null
        const blob = new Blob(chunks, { type: recorder.mimeType || mimeType })
        if (!blob.size) this.callbacks.failed('O navegador não produziu áudio. Tente gravar novamente.')
        else this.callbacks.finished(blob, Math.min(maxDuration, duration))
      }
      recorder.onerror = () => {
        if (!current()) return
        this.cancel()
        this.callbacks.failed('A gravação foi interrompida pelo navegador. Tente novamente.')
      }
      this.started = performance.now()
      this.duration = 0
      recorder.start()
      this.timer = setTimeout(() => this.stop(), maxDuration)
      this.callbacks.started()
    } catch (error) {
      if (!current()) return
      this.cancel()
      this.callbacks.failed(error instanceof Error && error.message.startsWith('Nenhum formato')
        ? error.message : 'Não foi possível acessar o microfone. Confira a permissão do navegador.')
    }
  }
}
