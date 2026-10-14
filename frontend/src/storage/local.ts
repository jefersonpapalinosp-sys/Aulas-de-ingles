/** Não simula persistência em memória: o chamador precisa distinguir falha de
 * chave ausente e só anunciar salvamento quando ok=true. Não registra textos. */
export type StorageResult<T> = { ok: true; value: T } | { ok: false; error: string }

function run<T>(operation: 'ler' | 'gravar' | 'remover', action: (storage: Storage) => T): StorageResult<T> {
  try {
    return { ok: true, value: action(window.localStorage) }
  } catch (error) {
    if (operation === 'remover') return { ok: false, error: 'Não foi possível remover a cópia local. Confira os dados ao reabrir.' }
    const quota = error instanceof DOMException && error.name === 'QuotaExceededError'
    return { ok: false, error: quota
      ? 'Armazenamento cheio; gravação local não confirmada.'
      : `Não foi possível ${operation} dados locais. Armazenamento indisponível.` }
  }
}

export const readLocal = (key: string): StorageResult<string | null> => run('ler', (s) => s.getItem(key))
export const writeLocal = (key: string, value: string): StorageResult<void> => run('gravar', (s) => s.setItem(key, value))
export const removeLocal = (key: string): StorageResult<void> => run('remover', (s) => s.removeItem(key))
