/** Usa somente vozes locais: texto do diálogo não vai para outro serviço de voz. */
export class PartnerSpeech {
  private generation = 0
  constructor(private finished: () => void) {}
  cancel() {
    this.generation++
    if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel()
  }
  play(text: string, rate: number): boolean {
    this.cancel()
    if (typeof speechSynthesis === 'undefined' || typeof SpeechSynthesisUtterance === 'undefined') return false
    const voice = speechSynthesis.getVoices().find((item) => item.localService && /^en[-_]US$/i.test(item.lang))
    if (!voice) return false
    const generation = this.generation
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.voice = voice
    utterance.lang = 'en-US'
    utterance.rate = Math.max(0.5, Math.min(1.5, rate))
    utterance.onend = utterance.onerror = () => { if (this.generation === generation) this.finished() }
    try { speechSynthesis.speak(utterance); return true }
    catch { return false }
  }
}
