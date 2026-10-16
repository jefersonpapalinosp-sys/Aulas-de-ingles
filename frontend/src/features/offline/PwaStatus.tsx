import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { inspectCache, PWA_EVENT, registrationError, type CacheStatus } from './pwa'

export function PwaStatus() {
  const { pathname } = useLocation()
  const match = /^\/cursos\/([a-z0-9-]+)\/aulas\/(\d+)(?:\/|$)/.exec(pathname)
  const lessonPath = match ? `/api/courses/${match[1]}/lessons/${match[2]}` : undefined
  const [snapshot, setSnapshot] = useState<CacheStatus | null>(null)
  const [waiting, setWaiting] = useState(false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  const invalidate = useCallback(() => { generation.current++ }, [])
  const refresh = useCallback(async () => {
    const current = ++generation.current
    try {
      const registration = await navigator.serviceWorker?.getRegistration()
      if (current !== generation.current) return
      setWaiting(Boolean(registration?.waiting))
      const result = await inspectCache('PWA_STATUS', lessonPath)
      if (current === generation.current) setSnapshot(result)
    } catch { if (current === generation.current) setSnapshot(null) }
  }, [lessonPath])
  useEffect(() => {
    setSnapshot(null)
    void refresh()
    // Aguarda a consulta editorial disparada pela rota; o botão permite reconferir.
    const timer = setTimeout(() => { void refresh() }, 1500)
    const listener = () => { void refresh() }
    window.addEventListener(PWA_EVENT, listener)
    window.addEventListener('focus', listener)
    return () => {
      invalidate()
      clearTimeout(timer)
      window.removeEventListener(PWA_EVENT, listener)
      window.removeEventListener('focus', listener)
    }
  }, [refresh, invalidate])

  async function check() {
    setBusy(true)
    setMessage('')
    try {
      await (await navigator.serviceWorker?.getRegistration())?.update()
      await refresh()
    } catch { setMessage('Sem conexão para verificar uma nova versão.'); await refresh() }
    finally { setBusy(false) }
  }
  async function clear() {
    if (!window.confirm('Remover apenas os textos públicos deste dispositivo? Rascunhos, gravações e respostas pendentes não serão apagados.')) return
    setBusy(true)
    try {
      setSnapshot(await inspectCache('PWA_CLEAR_TEXT', lessonPath))
      setMessage('Textos removidos. Uma consulta online poderá armazená-los novamente.')
    } catch { setMessage('Não foi possível limpar os textos. Tente novamente.') }
    finally { setBusy(false) }
  }

  return (
    <aside className="pwa-status" aria-label="Disponibilidade offline e versão">
      {waiting && <p role="status">Atualização disponível. Salve seus textos e envie ou baixe as gravações pendentes. Depois feche todas as abas e janelas deste aplicativo e abra novamente. Nada será recarregado automaticamente. Após atualizar, abra as aulas com conexão novamente.</p>}
      <details>
        <summary>Offline e atualizações</summary>
        {snapshot ? <>
          <p>{snapshot.count} respostas públicas armazenadas ({Math.ceil(snapshot.bytes / 1024)} KiB). Limite: 120 respostas ou 8 MiB; validade de até 7 dias.</p>
          {lessonPath && <p>{snapshot.lesson
            ? `Texto desta aula armazenado até ${new Date(snapshot.expiresAt!).toLocaleString('pt-BR')}.`
            : 'Texto desta aula não armazenado. Abra a aula com conexão e verifique novamente.'}</p>}
          {snapshot.cacheUnavailable && <p>O armazenamento apresentou uma falha. Não conte com a disponibilidade offline.</p>}
          <p className="muted">Versão {snapshot.version}</p>
        </> : <p>{registrationError ? 'Não foi possível instalar o modo offline.' : 'Disponibilidade offline não confirmada. Use a versão instalada/build com conexão para preparar o cache.'}</p>}
        <p>Somente textos públicos já abertos e telas carregadas podem funcionar sem rede. Áudio e vídeo continuam online. Gravações locais não entram na fila de exercícios: envie ou baixe antes de fechar a aba.</p>
        <p>O navegador pode liberar esse armazenamento. O cache não é backup e não inclui dados privados da conta.</p>
        <div className="pwa-actions">
          <button type="button" onClick={() => { void check() }} disabled={busy}>Verificar disponibilidade e versão</button>
          <button type="button" onClick={() => { void clear() }} disabled={busy || !snapshot}>Limpar somente textos públicos</button>
        </div>
        {message && <p role="status">{message}</p>}
      </details>
    </aside>
  )
}
