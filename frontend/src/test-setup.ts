import '@testing-library/jest-dom/vitest'
import { IDBFactory } from 'fake-indexeddb'
import { beforeEach } from 'vitest'

beforeEach(() => {
  // Banco em memória NOVO por teste; nunca abre storage do navegador de estudo.
  Object.defineProperty(globalThis, 'indexedDB', { configurable: true, writable: true, value: new IDBFactory() })
  Object.defineProperty(globalThis, 'BroadcastChannel', { configurable: true, writable: true, value: undefined })
  const locks = new Map<string, Promise<unknown>>()
  Object.defineProperty(navigator, 'locks', { configurable: true, value: {
    request: <T,>(name: string, _options: unknown, callback: () => Promise<T>): Promise<T> => {
      const previous = locks.get(name) ?? Promise.resolve()
      const next = previous.catch(() => undefined).then(callback)
      locks.set(name, next)
      return next
    },
  } })
})
