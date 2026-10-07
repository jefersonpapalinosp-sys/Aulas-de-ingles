/** Cliente HTTP mínimo da S0. Na S2 os tipos passam a ser gerados do openapi.json. */

export type Health = {
  status: string
  db: string
  version: string | null
  env: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  let res: Response
  try {
    res = await fetch('/api/health', { signal })
  } catch {
    throw new ApiError('Não foi possível falar com a API.')
  }
  if (!res.ok && res.status !== 503) {
    throw new ApiError(`A API respondeu ${res.status}.`, res.status)
  }
  return (await res.json()) as Health
}
