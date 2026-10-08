import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, setAccessToken } from './client'

type Usuario = { id: number; email: string; display_name: string }

type Sessao = {
  usuario: Usuario | null
  carregando: boolean
  offline: boolean
  entrar: (email: string, senha: string) => Promise<void>
  registrar: (email: string, senha: string, nome: string) => Promise<void>
  sair: () => Promise<void>
}

const Ctx = createContext<Sessao | null>(null)

type Renovacao = { token: string | null; indisponivel: boolean }

const PERFIL_LOCAL = 'aulas:last-user:v1'
let renovacaoInicial: Promise<Renovacao> | null = null

function salvarPerfil(usuario: Usuario | null): void {
  if (usuario) {
    localStorage.setItem(
      PERFIL_LOCAL,
      JSON.stringify({ id: usuario.id, display_name: usuario.display_name }),
    )
  }
  else localStorage.removeItem(PERFIL_LOCAL)
}

function lerPerfil(): Usuario | null {
  try {
    const perfil: unknown = JSON.parse(localStorage.getItem(PERFIL_LOCAL) ?? 'null')
    if (
      typeof perfil === 'object' &&
      perfil !== null &&
      typeof (perfil as Usuario).id === 'number' &&
      typeof (perfil as Usuario).display_name === 'string'
    ) {
      return {
        id: (perfil as Usuario).id,
        display_name: (perfil as Usuario).display_name,
        email: '',
      }
    }
  } catch {
    // Um valor local inválido não deve impedir a tela de login.
  }
  return null
}

async function renovar(): Promise<Renovacao> {
  try {
    const { data, response } = await api.POST('/api/auth/refresh')
    return {
      token: data?.access_token ?? null,
      indisponivel: !data && response === undefined,
    }
  } catch {
    return { token: null, indisponivel: true }
  }
}

/**
 * O StrictMode monta, desmonta e monta o provider novamente em desenvolvimento.
 * O refresh é rotativo, portanto as duas montagens precisam compartilhar a
 * mesma chamada em vez de tentar consumir o mesmo cookie duas vezes.
 */
function renovarAoIniciar(): Promise<Renovacao> {
  if (!renovacaoInicial) {
    renovacaoInicial = renovar().finally(() => {
        renovacaoInicial = null
      })
  }
  return renovacaoInicial
}

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
  const [offline, setOffline] = useState(false)
  const qc = useQueryClient()

  const aplicar = useCallback(
    async (token: string) => {
      setAccessToken(token)
      const { data } = await api.GET('/api/auth/me')
      if (!data) throw new Error('Não foi possível carregar o perfil da sessão.')
      setUsuario(data)
      salvarPerfil(data)
      setOffline(false)
      await qc.invalidateQueries()
    },
    [qc],
  )

  useEffect(() => {
    let vivo = true
    void (async () => {
      const resultado = await renovarAoIniciar()
      if (!vivo) return
      if (resultado.token) {
        try {
          await aplicar(resultado.token)
        } catch {
          const perfil = lerPerfil()
          if (vivo && perfil) {
            setUsuario(perfil)
            setOffline(true)
          }
        }
      } else if (resultado.indisponivel || !navigator.onLine) {
        const perfil = lerPerfil()
        if (perfil) {
          setUsuario(perfil)
          setOffline(true)
        }
      }
      setCarregando(false)
    })()
    return () => {
      vivo = false
    }
  }, [aplicar])

  useEffect(() => {
    if (!offline) return
    const aoVoltar = () => {
      void (async () => {
        const resultado = await renovar()
        if (resultado.token) {
          await aplicar(resultado.token)
        } else if (!resultado.indisponivel) {
          setAccessToken(null)
          setUsuario(null)
          salvarPerfil(null)
          setOffline(false)
          qc.clear()
        }
      })()
    }
    window.addEventListener('online', aoVoltar)
    return () => window.removeEventListener('online', aoVoltar)
  }, [aplicar, offline, qc])

  const valor = useMemo<Sessao>(
    () => ({
      usuario,
      carregando,
      offline,
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
        try {
          await api.POST('/api/auth/logout')
        } finally {
          setAccessToken(null)
          setUsuario(null)
          salvarPerfil(null)
          setOffline(false)
          qc.clear()
        }
      },
    }),
    [usuario, carregando, offline, aplicar, qc],
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
