type Options = { reload?: () => void; signal?: AbortSignal }

const TIMEOUT = 30_000
const abortError = () => new DOMException('Atualização cancelada.', 'AbortError')

function bounded<T>(task: Promise<T>, signal?: AbortSignal, cleanup: () => void = () => undefined): Promise<T> {
  return new Promise((resolve, reject) => {
    let done = false
    const finish = (error?: Error, value?: T) => {
      if (done) return
      done = true
      clearTimeout(timer); signal?.removeEventListener('abort', abort); cleanup()
      if (error) reject(error); else resolve(value as T)
    }
    const abort = () => finish(abortError())
    const timer = setTimeout(() => finish(new Error('A atualização demorou demais. Tente novamente.')), TIMEOUT)
    signal?.addEventListener('abort', abort, { once: true })
    task.then((value) => finish(undefined, value), (cause) => finish(
      cause instanceof Error ? cause : new Error('Não foi possível atualizar.', { cause })))
    if (signal?.aborted) abort()
  })
}

function workerReady(worker: ServiceWorker, signal?: AbortSignal): Promise<void> {
  if (worker.state !== 'installing') return Promise.resolve()
  let changed: () => void = () => undefined
  return bounded(new Promise<void>((resolve, reject) => {
    changed = () => worker.state === 'redundant'
      ? reject(new Error('A nova versão não pôde ser instalada.'))
      : worker.state !== 'installing' && resolve()
    worker.addEventListener('statechange', changed); changed()
  }), signal, () => worker.removeEventListener('statechange', changed))
}

function controlledBy(container: ServiceWorkerContainer, worker: ServiceWorker,
  previous: ServiceWorker | null, signal?: AbortSignal): Promise<void> {
  if (container.controller !== previous && worker.state === 'activated') return Promise.resolve()
  let changed: () => void = () => undefined
  let stateChanged: () => void = () => undefined
  return bounded(new Promise<void>((resolve, reject) => {
    changed = () => {
      if (container.controller && container.controller !== previous && worker.state === 'activated') resolve()
    }
    stateChanged = () => worker.state === 'redundant'
      ? reject(new Error('A nova versão foi substituída. Tente novamente.')) : changed()
    container.addEventListener('controllerchange', changed)
    worker.addEventListener('statechange', stateChanged)
    if (worker.state === 'installed') worker.postMessage({ type: 'SKIP_WAITING' }); else changed()
  }), signal, () => {
    container.removeEventListener('controllerchange', changed)
    worker.removeEventListener('statechange', stateChanged)
  })
}

/** Busca, ativa e assume o worker novo antes da recarga; nunca limpa storage. */
export async function updateAppAndReload({ reload = () => window.location.reload(), signal }: Options = {}): Promise<void> {
  if (signal?.aborted) throw abortError()
  const container = navigator.serviceWorker
  if (!container) { reload(); return }
  const registration = await bounded(container.getRegistration(), signal)
  if (!registration) { reload(); return }
  const previous = container.controller
  if (!registration.waiting) {
    try { await bounded(registration.update(), signal) }
    catch (error) {
      if (signal?.aborted) throw abortError()
      throw new Error('Sem conexão para buscar a nova versão. Tente novamente.', { cause: error })
    }
  }
  let worker = registration.waiting ?? registration.installing
  if (worker) await workerReady(worker, signal)
  worker = registration.waiting ?? worker
  if (worker) await controlledBy(container, worker, previous, signal)
  if (signal?.aborted) throw abortError()
  reload()
}
