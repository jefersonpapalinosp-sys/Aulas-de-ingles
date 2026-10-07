import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, setAccessToken } from './client'

type Usuario = { id: number; email: string; display_name: string }

type Sessao = {
  usuario: Usuario | null
  carregando: boolean
  entrar: (email: string, senha: string) => Promise<void>
  registrar: (email: string, senha: string, nome: string) => Promise<void>
  sair: () => Promise<void>
}

const Ctx = createContext<Sessao | null>(null)

/**
 * Sessão do usuário.
 *
 * O access token fica **na memória**, nunca em localStorage: o que o
 * JavaScript consegue ler, um XSS também consegue. O refresh fica num cookie
 * httpOnly que o JS não enxerga e que só é enviado para /api/auth.
 *
 * Ao abrir a aplicação não há token em lugar nenhum — então a primeira coisa
 * que acontece é tentar um /refresh. Se o cookie ainda valer, a sessão volta.
 */
export function SessaoProvider({ children }: { children: React.ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null)
  const [carregando, setCarregando] = useState(true)
  const qc = useQueryClient()

  const aplicar = useCallback(
    async (token: string) => {
      setAccessToken(token)
      const { data } = await api.GET('/api/auth/me')
      setUsuario(data ?? null)
      await qc.invalidateQueries()
    },
    [qc],
  )

  useEffect(() => {
    let vivo = true
    void (async () => {
      const { data } = await api.POST('/api/auth/refresh')
      if (!vivo) return
      if (data) await aplicar(data.access_token)
      setCarregando(false)
    })()
    return () => {
      vivo = false
    }
  }, [aplicar])

  const valor = useMemo<Sessao>(
    () => ({
      usuario,
      carregando,
      entrar: async (email, password) => {
        const { data, response } = await api.POST('/api/auth/login', {
          body: { email, password },
        })
        if (!data) {
          throw new Error(
            response?.status === 401
              ? 'E-mail ou senha incorretos.'
              : 'Não foi possível entrar agora.',
          )
        }
        await aplicar(data.access_token)
      },
      registrar: async (email, password, display_name) => {
        const { data, response } = await api.POST('/api/auth/register', {
          body: { email, password, display_name },
        })
        if (!data) {
          throw new Error(
            response?.status === 409
              ? 'Já existe conta com esse e-mail.'
              : response?.status === 422
                ? 'A senha precisa de pelo menos 8 caracteres.'
                : 'Não foi possível criar a conta agora.',
          )
        }
        await aplicar(data.access_token)
      },
      sair: async () => {
        await api.POST('/api/auth/logout')
        setAccessToken(null)
        setUsuario(null)
        qc.clear()
      },
    }),
    [usuario, carregando, aplicar, qc],
  )

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>
}

export function useSessao(): Sessao {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useSessao precisa estar dentro de <SessaoProvider>')
  return ctx
}

export function useRenovacaoAutomatica() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.POST('/api/auth/refresh')
      if (!data) throw new Error('sessão expirada')
      setAccessToken(data.access_token)
      await qc.invalidateQueries()
    },
  })
}
