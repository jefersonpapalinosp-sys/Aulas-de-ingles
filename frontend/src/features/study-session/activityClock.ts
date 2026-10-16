/** Mede intervalos monotônicos contíguos. Suspensão e ausência não viram tempo ativo. */
export class ActivityClock {
  private last: number
  private active = false
  private duration = 0
  private end = 0
  constructor(private anchor: number, private emit: (end: number, duration: number) => void) {
    this.last = anchor
  }
  tick(now: number, active: boolean) {
    const delta = now - this.last
    if (active && this.active && delta > 0 && delta <= 2500) {
      this.duration += delta
      this.end = now - this.anchor
      if (this.duration >= 15000) this.flush()
    } else this.flush()
    this.last = now
    this.active = active
  }
  flush() {
    const duration = Math.floor(this.duration)
    if (duration > 0) this.emit(Math.floor(this.end), duration)
    this.duration = 0
  }
}
