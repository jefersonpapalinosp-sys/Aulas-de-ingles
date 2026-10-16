import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  api, onEstadoSessao, onSessaoPerdida, renovarSessao, setAccessToken,
  setSessionReadOnly, setSessionUser,
} from './client'
import { estadoIndisponivel, type EstadoSessao } from './session'
import { readLocal, removeLocal, writeLocal } from '../storage/local'

type Usuario = { id: number; email: string; display_name: string }

type Sessao = {
  usuario: Usuario | null
  carregando: boolean
  offline: boolean
  estado: EstadoSessao
  revalidando: boolean
  aviso: string | null
  revalidar: () => Promise<void>
  entrar: (email: string, senha: string) => Promise<void>
  registrar: (email: string, senha: string, nome: string) => Promise<void>
  sair: () => Promise<void>
  encerrarContaExcluida: (audioPendente: boolean) => void
}

const Ctx = createContext<Sessao | null>(null)

const PERFIL_LOCAL = 'aulas:last-user:v1'

function salvarPerfil(usuario: Usuario | null): boolean {
  return (usuario
    ? writeLocal(PERFIL_LOCAL, JSON.stringify({ id: usuario.id, display_name: usuario.display_name }))
    : removeLocal(PERFIL_LOCAL)).ok
}

function lerPerfil(onError?: (message: string) => void): Usuario | null {
  try {
    const local = readLocal(PERFIL_LOCAL)
    if (!local.ok) { onError?.(local.error); return null }
    const perfil: unknown = JSON.parse(local.value ?? 'null')
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
    onError?.('Perfil local inválido. Entre na mesma conta.')
  }
  return null
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
  const [estado, setEstado] = useState<EstadoSessao>('expirada')
  const [revalidando, setRevalidando] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)
  const vivo = useRef(false)
  const operacao = useRef(0)
  const perfilAtual = useRef<Usuario | null>(null)
  const perfilConfirmado = useRef(false)
  const qc = useQueryClient()

  const guardarPerfil = useCallback((perfil: Usuario | null) => {
    setAviso(salvarPerfil(perfil) ? null
      : 'O armazenamento deste navegador está indisponível. O perfil local não pôde ser atualizado.')
  }, [])

  const limpar = useCallback(() => {
    operacao.current += 1
    setAccessToken(null)
    setSessionUser(null)
    setSessionReadOnly(true)
    perfilAtual.current = null
    perfilConfirmado.current = false
    setUsuario(null)
    setEstado('expirada')
    setCarregando(false)
    setRevalidando(false)
    guardarPerfil(null)
    qc.clear()
  }, [guardarPerfil, qc])

  const aplicar = useCallback(
    async (token: string, pedido: number) => {
      setAccessToken(token)
      setSessionReadOnly(true)
      const { data, response } = await api.GET('/api/auth/me')
      if (!vivo.current || operacao.current !== pedido) return
      if (response?.status === 401) { limpar(); return }
      if (!data) throw new Error('Não foi possível carregar o perfil da sessão.')
      const mudouConta = perfilAtual.current?.id !== data.id
      if (mudouConta) qc.clear()
      perfilAtual.current = data
      perfilConfirmado.current = true
      setSessionUser(data.id)
      setSessionReadOnly(false)
      setUsuario(data)
      guardarPerfil(data)
      setEstado('valida')
      // Não refazer queries da conta anterior antes de o React trocar a árvore.
      if (!mudouConta) await qc.invalidateQueries()
    },
    [guardarPerfil, limpar, qc],
  )

  const manterLocal = useCallback(() => {
    const perfil = perfilAtual.current ?? lerPerfil(setAviso)
    perfilAtual.current = perfil
    setUsuario(perfil)
    setSessionUser(perfil?.id ?? null)
    setSessionReadOnly(true)
    setEstado(estadoIndisponivel())
  }, [])

  const revalidar = useCallback(async () => {
    const pedido = ++operacao.current
    setRevalidando(true)
    try {
      const resultado = await renovarSessao()
      if (!vivo.current || pedido !== operacao.current) return
      if (resultado.estado === 'valida') await aplicar(resultado.token, pedido)
      else if (resultado.estado === 'expirada') limpar()
      else if (resultado.estado !== 'substituida') manterLocal()
    } catch {
      if (vivo.current && pedido === operacao.current) manterLocal()
    } finally {
      if (vivo.current && pedido === operacao.current) {
        setCarregando(false)
        setRevalidando(false)
      }
    }
  }, [aplicar, limpar, manterLocal])

  useEffect(() => {
    vivo.current = true
    setSessionReadOnly(true)
    setSessionUser(lerPerfil(setAviso)?.id ?? null)
    onSessaoPerdida(limpar)
    onEstadoSessao((novo) => {
      if (novo === 'valida') {
        if (perfilConfirmado.current) {
          setSessionReadOnly(false)
          setEstado(novo)
        }
      } else if (novo !== 'expirada') {
        setSessionReadOnly(true)
        setEstado(novo)
      }
    })
    void revalidar()
    return () => {
      vivo.current = false
      operacao.current += 1
      onSessaoPerdida(null)
      onEstadoSessao(null)
    }
  }, [limpar, revalidar])

  useEffect(() => {
    if (estado !== 'offline' && estado !== 'indisponivel') return
    const aoVoltar = () => { void revalidar() }
    window.addEventListener('online', aoVoltar)
    return () => window.removeEventListener('online', aoVoltar)
  }, [estado, revalidar])

  const valor = useMemo<Sessao>(
    () => ({
      usuario,
      carregando,
      offline: estado === 'offline' || estado === 'indisponivel',
      estado,
      revalidando,
      aviso,
      revalidar,
      entrar: async (email, password) => {
        const pedido = ++operacao.current
        setAccessToken(null)
        setSessionUser(null)
        setSessionReadOnly(true)
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
        if (vivo.current && pedido === operacao.current) await aplicar(data.access_token, pedido)
      },
      registrar: async (email, password, display_name) => {
        const pedido = ++operacao.current
        setAccessToken(null)
        setSessionUser(null)
        setSessionReadOnly(true)
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
        if (vivo.current && pedido === operacao.current) await aplicar(data.access_token, pedido)
      },
      sair: async () => {
        limpar()
        const pedido = operacao.current
        try {
          const { response } = await api.POST('/api/auth/logout')
          if (!response.ok) throw new Error('Logout remoto indisponível.')
        } catch {
          if (vivo.current && operacao.current === pedido) {
            setAviso('Você saiu deste dispositivo, mas não foi possível confirmar o encerramento no servidor.')
          }
        }
      },
      encerrarContaExcluida: (audioPendente) => {
        limpar()
        setAviso(`A conta foi excluída.${audioPendente ? ' A limpeza dos áudios foi agendada.' : ''} Cópias baixadas e dados de outros dispositivos não podem ser removidos daqui.`)
      },
    }),
    [usuario, carregando, estado, revalidando, aviso, revalidar, aplicar, limpar],
  )

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>
}

export function useSessao(): Sessao {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useSessao precisa estar dentro de <SessaoProvider>')
  return ctx
}
