import { afterEach, describe, expect, it, vi } from 'vitest'
import { updateAppAndReload } from './appUpdate'

type WorkerFixture = ServiceWorker & {
  postSpy: ReturnType<typeof vi.fn>
  setState: (state: ServiceWorkerState) => void
}
type ContainerFixture = ServiceWorkerContainer & { removeSpy: ReturnType<typeof vi.fn> }

function worker(initial: ServiceWorkerState, postMessage = vi.fn()): WorkerFixture {
  const target = new EventTarget()
  let state = initial
  return {
    get state() { return state },
    setState(next: ServiceWorkerState) { state = next; target.dispatchEvent(new Event('statechange')) },
    postMessage,
    postSpy: postMessage,
    addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target),
    dispatchEvent: target.dispatchEvent.bind(target),
    onstatechange: null, onerror: null, scriptURL: '/sw.js',
  }
}

function platform(registration?: object) {
  const target = new EventTarget()
  const removeSpy = vi.fn(target.removeEventListener.bind(target))
  const container = {
    controller: null,
    getRegistration: vi.fn().mockResolvedValue(registration),
    addEventListener: vi.fn(target.addEventListener.bind(target)),
    removeEventListener: removeSpy,
    removeSpy,
    dispatchEvent: target.dispatchEvent.bind(target),
  } as unknown as ContainerFixture
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: container })
  return container
}

afterEach(() => {
  vi.restoreAllMocks(); localStorage.clear()
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: undefined })
})

describe('atualização confirmada do aplicativo', () => {
  it('sem service worker faz recarga comum e não toca no storage', async () => {
    localStorage.setItem('pending', 'preservado')
    const reload = vi.fn()
    await updateAppAndReload({ reload })
    expect(reload).toHaveBeenCalledOnce()
    expect(localStorage.getItem('pending')).toBe('preservado')
  })

  it('busca a release, envia SKIP_WAITING, espera o worker alvo e só então recarrega', async () => {
    const order: string[] = []
    let available: WorkerFixture | null = null
    const waiting = worker('installed', vi.fn(() => {
      order.push('skip-waiting')
      Object.defineProperty(container, 'controller', { configurable: true, value: waiting })
      waiting.setState('activated')
      container.dispatchEvent(new Event('controllerchange'))
    }))
    const container = platform({ get waiting() { return available }, installing: null,
      update: vi.fn(() => { order.push('update'); available = waiting; return Promise.resolve() }) })
    localStorage.setItem('queue', 'resposta pendente')
    await updateAppAndReload({ reload: () => order.push('reload') })
    expect(waiting.postSpy).toHaveBeenCalledWith({ type: 'SKIP_WAITING' })
    expect(order).toEqual(['update', 'skip-waiting', 'reload'])
    expect(localStorage.getItem('queue')).toBe('resposta pendente')
  })

  it('aguarda o worker em instalação antes de ativar', async () => {
    const installing = worker('installing', vi.fn(() => {
      Object.defineProperty(container, 'controller', { configurable: true, value: installing })
      installing.setState('activated')
      container.dispatchEvent(new Event('controllerchange'))
    }))
    const registration = { get waiting() { return installing.state === 'installed' ? installing : null },
      installing, update: vi.fn(() => Promise.resolve()) }
    const container = platform(registration)
    const reload = vi.fn()
    const result = updateAppAndReload({ reload })
    installing.setState('installed')
    await result
    expect(installing.postSpy).toHaveBeenCalledWith({ type: 'SKIP_WAITING' })
    expect(reload).toHaveBeenCalledOnce()
  })

  it('falha de rede não recarrega nem remove dados pendentes', async () => {
    platform({ waiting: null, installing: null,
      update: vi.fn().mockRejectedValue(new TypeError('offline')) })
    const reload = vi.fn()
    localStorage.setItem('draft', 'texto local')
    await expect(updateAppAndReload({ reload })).rejects.toThrow('Sem conexão')
    expect(reload).not.toHaveBeenCalled()
    expect(localStorage.getItem('draft')).toBe('texto local')
  })

  it('sem nova release recarrega sem confundir wrappers do worker ativo', async () => {
    const current = worker('activated')
    const activeWrapper = worker('activated')
    const update = vi.fn().mockResolvedValue(undefined)
    const container = platform({ waiting: null, installing: null, active: activeWrapper, update })
    Object.defineProperty(container, 'controller', { configurable: true, value: current })
    const reload = vi.fn()
    await updateAppAndReload({ reload })
    expect(update).toHaveBeenCalledOnce()
    expect(reload).toHaveBeenCalledOnce()
  })

  it('ativa worker já instalado mesmo offline sem tentar nova busca', async () => {
    const update = vi.fn().mockRejectedValue(new TypeError('offline'))
    const waiting = worker('installed', vi.fn(() => {
      Object.defineProperty(container, 'controller', { configurable: true, value: waiting })
      waiting.setState('activated')
      container.dispatchEvent(new Event('controllerchange'))
    }))
    const container = platform({ waiting, installing: null, update })
    const reload = vi.fn()
    await updateAppAndReload({ reload })
    expect(update).not.toHaveBeenCalled()
    expect(waiting.postSpy).toHaveBeenCalledWith({ type: 'SKIP_WAITING' })
    expect(reload).toHaveBeenCalledOnce()
  })

  it('aborto remove listener de controllerchange e não recarrega', async () => {
    const waiting = worker('installed')
    const container = platform({ waiting, installing: null, update: vi.fn().mockResolvedValue(undefined) })
    const reload = vi.fn()
    const controller = new AbortController()
    const result = updateAppAndReload({ reload, signal: controller.signal })
    await vi.waitFor(() => expect(waiting.postSpy).toHaveBeenCalled())
    controller.abort()
    await expect(result).rejects.toMatchObject({ name: 'AbortError' })
    expect(container.removeSpy.mock.calls).toContainEqual(
      ['controllerchange', expect.any(Function)])
    expect(reload).not.toHaveBeenCalled()
  })
})
