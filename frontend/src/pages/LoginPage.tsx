import { useEffect, useRef, useState } from 'react'
import { useSessao } from '../api/auth'

export function LoginPage() {
  const { entrar, registrar } = useSessao()
  const [modo, setModo] = useState<'entrar' | 'criar'>('entrar')
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [nome, setNome] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const nomeInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (modo === 'criar') {
      nomeInputRef.current?.focus({ preventScroll: true })
      window.scrollTo({ top: 0, left: 0 })
    }
  }, [modo])

  async function enviar(e: React.FormEvent) {
    e.preventDefault()
    setErro(null)
    setEnviando(true)
    try {
      if (modo === 'entrar') await entrar(email, senha)
      else await registrar(email, senha, nome)
    } catch (err) {
      setErro(err instanceof Error ? err.message : 'Algo deu errado.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="login-tela">
      <div className="login-caixa">
        <p className="brand">VOA · Let's Learn English · Level 1</p>
        <h1>Aulas de Inglês</h1>
        <p className="lead">
          {modo === 'entrar'
            ? 'Entre para marcar aulas estudadas e guardar suas tentativas.'
            : 'Crie uma conta para o seu progresso ficar guardado.'}
        </p>

        <form onSubmit={enviar}>
          {modo === 'criar' && (
            <label>
              Nome
              <input
                ref={nomeInputRef}
                type="text"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                required
                autoComplete="name"
              />
            </label>
          )}
          <label>
            E-mail
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </label>
          <label>
            Senha
            <input
              type="password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
              minLength={8}
              autoComplete={modo === 'entrar' ? 'current-password' : 'new-password'}
            />
            {modo === 'criar' && <small>No mínimo 8 caracteres.</small>}
          </label>

          {erro && (
            <p className="erro" role="alert">
              {erro}
            </p>
          )}

          <button type="submit" disabled={enviando}>
            {enviando ? 'Aguarde…' : modo === 'entrar' ? 'Entrar' : 'Criar conta'}
          </button>
        </form>

        <button
          type="button"
          className="trocar-modo"
          onClick={() => {
            setModo(modo === 'entrar' ? 'criar' : 'entrar')
            setErro(null)
          }}
        >
          {modo === 'entrar' ? 'Ainda não tenho conta' : 'Já tenho conta'}
        </button>
      </div>
    </div>
  )
}
