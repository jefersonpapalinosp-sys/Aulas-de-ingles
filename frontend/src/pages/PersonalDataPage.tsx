import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useSessao } from '../api/auth'
import { authenticatedFetch } from '../api/client'
import type { components } from '../api/schema'
import { subscribeAttemptQueue } from '../features/offline/attemptQueue'
import { inspectCache } from '../features/offline/pwa'
import { inspectDevice, type DeviceInventory } from '../features/privacy/deviceInventory'

type Export = components['schemas']['PersonalDataExportOut']
type Audio = components['schemas']['AudioExportEntry']

export function PersonalDataPage() {
  const { usuario, offline } = useSessao()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [manifest, setManifest] = useState<Audio[] | null>(null)
  const [exportedAt, setExportedAt] = useState('')
  const [inventory, setInventory] = useState<DeviceInventory | null>(null)
  const [localMessage, setLocalMessage] = useState('')
  const [clearing, setClearing] = useState(false)
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
        </div>
        <p role="status">{localMessage}</p>
        <p>Essa limpeza não remove rascunhos, respostas, gravações, progresso ou dados da conta. A exclusão integral de conta ainda não está disponível neste incremento.</p>
      </section>
      <Link to="/caderno">Voltar ao caderno e ao histórico</Link>
    </div>
  )
}
