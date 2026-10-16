import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSessao } from '../api/auth'
import { authenticatedFetch } from '../api/client'
import type { components } from '../api/schema'
import { subscribeAttemptQueue } from '../features/offline/attemptQueue'
import { inspectCache } from '../features/offline/pwa'
import {
  clearDeviceData,
  inspectDevice,
  type DeviceInventory,
} from '../features/privacy/deviceInventory'

type Export = components['schemas']['PersonalDataExportOut']
type Audio = components['schemas']['AudioExportEntry']

export function PersonalDataPage() {
  const { usuario, offline, encerrarContaExcluida } = useSessao()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [manifest, setManifest] = useState<Audio[] | null>(null)
  const [exportedAt, setExportedAt] = useState('')
  const [inventory, setInventory] = useState<DeviceInventory | null>(null)
  const [localMessage, setLocalMessage] = useState('')
  const [clearing, setClearing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [deletionError, setDeletionError] = useState('')
  const active = useRef<AbortController | null>(null)
  const releases = useRef<(() => void)[]>([])
  const generation = useRef(0)
  const userId = usuario?.id
  const invalidate = useCallback(() => { generation.current++ }, [])

  const refresh = useCallback(async () => {
    if (userId === undefined) return
    const current = ++generation.current
    const result = await inspectDevice(userId)
    if (current === generation.current) setInventory(result)
  }, [userId])
  useEffect(() => {
    void refresh()
    const update = () => { void refresh() }
    const unsubscribe = subscribeAttemptQueue(update)
    window.addEventListener('storage', update)
    window.addEventListener('focus', update)
    return () => {
      invalidate()
      active.current?.abort()
      releases.current.forEach((release) => release())
      releases.current = []
      unsubscribe()
      window.removeEventListener('storage', update)
      window.removeEventListener('focus', update)
    }
  }, [refresh, invalidate])

  function save(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    const timer = window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    releases.current.push(() => { clearTimeout(timer); URL.revokeObjectURL(url) })
  }

  async function download(audio?: Audio) {
    if (active.current || offline) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true)
    setError('')
    setMessage(audio ? 'Preparando áudio…' : 'Preparando exportação consistente da conta…')
    try {
      // Nunca seguir URL fornecida por um arquivo importado ou expor credenciais em links.
      const path = audio ? `/api/speaking/attempts/${audio.attempt_id}/audio` : '/api/me/export'
      const response = await authenticatedFetch(path, { signal: controller.signal, cache: 'no-store' })
      if (!response.ok) {
        if (response.status === 413) throw new Error('A conta excede o limite desta exportação (10 mil registros ou 20 MiB). Nenhum arquivo parcial foi gerado. Solicite ajuda ao responsável pelo sistema.')
        if (audio && [404, 409].includes(response.status)) throw new Error('Este áudio não está disponível ou sua integridade não foi confirmada. Preserve qualquer cópia local e atualize a exportação.')
        throw new Error('Não foi possível baixar agora. Verifique sua conexão e sessão e tente novamente.')
      }
      if (audio) {
        const blob = await response.blob()
        controller.signal.throwIfAborted()
        const ext = ({ 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a', 'audio/mpeg': 'mp3', 'audio/wav': 'wav' } as Record<string, string>)[audio.mime_type?.split(';')[0] ?? ''] ?? 'audio'
        save(blob, `gravacao-${audio.attempt_id}.${ext}`)
      } else {
        const raw = await response.text()
        const data = JSON.parse(raw) as Export
        controller.signal.throwIfAborted()
        if (data.schema_version !== '2.0' || !Array.isArray(data.audio_manifest) || !data.scope) throw new Error('Formato de exportação incompatível. Atualize a aplicação e tente novamente.')
        save(new Blob([raw], { type: 'application/json' }), 'aulas-ingles-dados.json')
        setManifest(data.audio_manifest)
        setExportedAt(data.scope.snapshot_at)
      }
      setMessage('Download solicitado. Confira os downloads do navegador; o salvamento no dispositivo não pode ser confirmado aqui.')
    } catch (cause) {
      if (!controller.signal.aborted) {
        setMessage('')
        setError(cause instanceof Error ? cause.message : 'Falha no download. Tente novamente.')
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false)
      if (active.current === controller) active.current = null
    }
  }

  async function clearPublicText() {
    if (!window.confirm('Remover somente textos públicos deste navegador? Rascunhos, respostas pendentes, gravações e dados da conta serão preservados.')) return
    setClearing(true)
    try {
      await inspectCache('PWA_CLEAR_TEXT')
      setLocalMessage('Textos públicos removidos. Nenhum dado pessoal ou remoto foi apagado. Aulas abertas online poderão ser armazenadas novamente.')
    } catch { setLocalMessage('Não foi possível confirmar a limpeza dos textos públicos. Nenhum dado pessoal foi removido por esta ação.') }
    finally { setClearing(false); void refresh() }
  }

  async function clearPrivateData() {
    if (userId === undefined || !window.confirm('Apagar deste navegador os rascunhos, respostas pendentes, posições, progresso e a gravação temporária desta conta? Dados não enviados serão perdidos.')) return
    setClearing(true)
    setLocalMessage('')
    try {
      const removed = await clearDeviceData(userId)
      setLocalMessage(`${removed} item(ns) local(is) removido(s). A conta e os dados do servidor foram preservados.`)
    } catch {
      setLocalMessage('A limpeza local não pôde ser confirmada por completo. Feche outras abas, atualize o inventário e tente novamente.')
    } finally { setClearing(false); void refresh() }
  }

  async function deleteAccount(event: React.FormEvent) {
    event.preventDefault()
    if (offline || confirmation !== 'EXCLUIR MINHA CONTA'
      || !window.confirm('Excluir definitivamente a conta e os dados enviados ao servidor? Esta ação não pode ser desfeita.')) return
    setDeleting(true)
    setDeletionError('')
    try {
      const response = await authenticatedFetch('/api/me/account', {
        method: 'DELETE', cache: 'no-store', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operation_key: crypto.randomUUID(), password, confirmation }),
      })
      if (!response.ok) {
        if (response.status === 401) throw new Error('Senha incorreta. A conta não foi excluída.')
        if (response.status === 409) throw new Error('A sessão mudou. Entre novamente antes de excluir a conta.')
        throw new Error('Não foi possível confirmar a exclusão. A conta foi preservada; tente novamente.')
      }
      const result = await response.json() as { state?: string; database_deleted?: boolean }
      if (result.database_deleted !== true || !['completed', 'cleanup_pending'].includes(result.state ?? '')) {
        throw new Error('O servidor não confirmou a exclusão. Entre novamente para conferir a conta.')
      }
      encerrarContaExcluida(result.state === 'cleanup_pending')
    } catch (cause) {
      setDeletionError(cause instanceof Error ? cause.message : 'Falha ao excluir a conta.')
    } finally {
      setPassword('')
      setDeleting(false)
    }
  }

  const count = (value: number | null | undefined) => value ?? 'Não confirmado'
  return (
    <div className="personal-data-page">
      <header>
        <p className="eyebrow">Privacidade e portabilidade · Sprint 40</p>
        <h1>Meus dados</h1>
        <p className="lead">Veja o que está na sua conta e o que ainda depende deste navegador.</p>
      </header>
      <section className="data-panel" aria-labelledby="account-export-title">
        <h2 id="account-export-title">Exportar dados da conta</h2>
        <p>O JSON inclui perfil, progresso, tempo ativo, revisões, checkpoints, sessões de prática, textos, versões de escrita, feedbacks, caderno e metadados de voz. Inclui também uso da assistência e datas das sessões de acesso, sem credenciais.</p>
        <p><strong>Não é um backup restaurável da conta.</strong> Não inclui os arquivos de áudio, transcrições já expiradas nem alterações ainda não enviadas deste dispositivo. A exportação atual é limitada a 10 mil registros e 20 MiB; contas maiores não recebem um arquivo parcial.</p>
        <p>O arquivo contém textos e dados pessoais. Guarde-o em local protegido. Não armazenamos uma cópia da exportação no servidor; o arquivo baixado não expira e não pode ser apagado remotamente.</p>
        <button className="btn" type="button" disabled={busy || offline} onClick={() => { void download() }}>
          {busy ? 'Preparando download…' : 'Baixar meus dados em JSON'}
        </button>
        {offline && <p role="status">Conecte-se e confirme sua sessão para exportar os dados da conta.</p>}
        <p role="status" aria-live="polite">{message}</p>
        {error && <p role="alert" className="erro">{error}</p>}
        {exportedAt && <p>Snapshot da conta: <time dateTime={exportedAt}>{new Date(exportedAt).toLocaleString('pt-BR')}</time>. Mudanças posteriores entram em uma nova exportação.</p>}
      </section>
      <section className="data-panel" aria-labelledby="audio-export-title">
        <h2 id="audio-export-title">Áudios pessoais, separadamente</h2>
        <p>Após exportar o JSON, baixe cada gravação abaixo. Os caminhos do manifesto exigem a mesma conta autenticada: não são links públicos. A disponibilidade e a integridade são conferidas novamente a cada download.</p>
        {manifest === null ? <p>Exporte os dados da conta para consultar o manifesto de áudio.</p>
          : manifest.length === 0 ? <p>Nenhuma gravação registrada neste snapshot.</p>
          : <ul className="data-audio-list">{manifest.map((audio) => <li key={audio.attempt_id}>
            <span>Gravação {audio.attempt_id} · {audio.file_size ? `${Math.ceil(audio.file_size / 1024)} KiB` : 'sem arquivo confirmado'}</span>
            {audio.download_path ? <button type="button" disabled={busy || offline} onClick={() => { void download(audio) }}>Baixar gravação {audio.attempt_id}</button>
              : <span>Download indisponível neste snapshot. O envio pode estar pendente ou o arquivo exigir recuperação.</span>}
          </li>)}</ul>}
      </section>
      <section className="data-panel" aria-labelledby="device-data-title">
        <h2 id="device-data-title">Dados deste dispositivo</h2>
        <p>Contagens da conta atual neste navegador, não uma confirmação de sincronização. Cópias locais podem coincidir com dados já enviados; itens inválidos são preservados.</p>
        <dl className="data-inventory">
          <div><dt>Rascunhos de escrita locais</dt><dd>{count(inventory?.drafts)}</dd></div>
          <div><dt>Respostas pendentes de envio</dt><dd>{count(inventory?.pendingAnswers)}</dd></div>
          <div><dt>Respostas bloqueadas para revisão</dt><dd>{count(inventory?.blockedAnswers)}</dd></div>
          <div><dt>Comandos de posição de áudio locais</dt><dd>{count(inventory?.mediaCommands)}</dd></div>
          <div><dt>Eventos de tempo ativo locais</dt><dd>{count(inventory?.activityEvents)}</dd></div>
          <div><dt>Cópias de progresso, posição e autoavaliação</dt><dd>{count(inventory?.localCopies)}</dd></div>
        </dl>
        {inventory?.voiceDraft && <p role="status">Há uma gravação temporária de recuperação nesta aba. Volte à mesma aula para enviá-la ou baixá-la antes que expire (até cinco minutos).</p>}
        <p>Não conseguimos inventariar gravações em outras abas nem dados que o navegador não conseguiu gravar. Confira suas aulas antes de fechar abas ou apagar dados pelo navegador. Gravações temporárias não são backup.</p>
        <div className="pwa-actions">
          <button type="button" onClick={() => { void refresh() }}>Atualizar inventário local</button>
          <button type="button" disabled={clearing} onClick={() => { void clearPublicText() }}>Limpar somente textos públicos deste navegador</button>
          <button type="button" disabled={clearing} onClick={() => { void clearPrivateData() }}>Apagar dados locais desta conta</button>
        </div>
        <p role="status">{localMessage}</p>
        <p>Feche outras abas antes da limpeza privada. Ela não apaga o servidor, outros dispositivos, downloads nem o cache público das aulas.</p>
      </section>
      <section className="data-panel estado-erro" aria-labelledby="delete-account-title">
        <h2 id="delete-account-title">Excluir conta</h2>
        <p>A exclusão remove o perfil e os dados enviados ao servidor. Áudios são removidos por uma tarefa retomável. Backups de desenvolvimento podem conservar uma cópia temporária conforme a política de retenção.</p>
        <p>Dados deste navegador, de outras abas ou dispositivos e arquivos que você baixou exigem limpeza separada.</p>
        <form onSubmit={(event) => { void deleteAccount(event) }}>
          <label>Senha atual
            <input type="password" autoComplete="current-password" minLength={8} required
              value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <label>Digite <strong>EXCLUIR MINHA CONTA</strong>
            <input type="text" autoComplete="off" required value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)} />
          </label>
          <button type="submit" disabled={deleting || offline || confirmation !== 'EXCLUIR MINHA CONTA'}>
            {deleting ? 'Excluindo conta…' : 'Excluir minha conta definitivamente'}
          </button>
        </form>
        {offline && <p role="status">Conecte-se e confirme a sessão para excluir a conta.</p>}
        {deletionError && <p role="alert" className="erro">{deletionError}</p>}
      </section>
      <Link to="/caderno">Voltar ao caderno e ao histórico</Link>
    </div>
  )
}
