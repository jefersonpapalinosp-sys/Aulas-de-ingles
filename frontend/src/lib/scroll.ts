/** Respeita a preferência do dispositivo também no scroll disparado por JS. */
export function scrollToTop() {
  window.scrollTo({ top: 0, behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
}
