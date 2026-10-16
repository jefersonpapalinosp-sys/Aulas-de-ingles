export const PWA_EVENT = 'aulas:pwa'
export let registrationError = false
export function registerPwa() {
  if (!('serviceWorker' in navigator) || !import.meta.env.PROD) return
  const notify = () => window.dispatchEvent(new Event(PWA_EVENT))
  void navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).then((registration) => {
    const watch = () => registration.installing?.addEventListener('statechange', notify)
    watch()
    registration.addEventListener('updatefound', () => { watch(); notify() })
    navigator.serviceWorker.addEventListener('controllerchange', notify)
    notify()
  }).catch(() => { registrationError = true; notify() })
}

export type CacheStatus = {
  version: string; count: number; bytes: number; lesson: boolean
  expiresAt: number | null; cacheUnavailable: boolean
}

export function inspectCache(type: 'PWA_STATUS' | 'PWA_CLEAR_TEXT', lessonPath?: string): Promise<CacheStatus> {
  return new Promise((resolve, reject) => {
    const worker = navigator.serviceWorker?.controller
    if (!worker) { reject(new Error('Worker não ativo')); return }
    const channel = new MessageChannel()
    const finish = () => { clearTimeout(timeout); channel.port1.close(); channel.port2.close() }
    const timeout = setTimeout(() => { finish(); reject(new Error('Cache não respondeu')) }, 2500)
    channel.port1.onmessage = ({ data }: MessageEvent<CacheStatus & { error?: boolean }>) => {
      finish()
      if (data.error || typeof data.version !== 'string') reject(new Error('Cache indisponível'))
      else resolve(data)
    }
    worker.postMessage({ type, lessonPath }, [channel.port2])
  })
}
