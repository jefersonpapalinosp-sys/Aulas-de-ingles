import { lazy, Suspense, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ErrorBoundary } from '../src/components/ErrorBoundary'
import '../src/styles.css'

// Fixture sem sessão ou API. Playwright bloqueia o módulo para provocar uma
// falha real de import dinâmico, sem editar build ou dados de estudo.
const Page = lazy(() => import('./recovery-page'))
function Harness() {
  const [page, setPage] = useState('home')
  return <>
    <nav aria-label="Navegação de teste"><button type="button" onClick={() => setPage('lesson')}>Abrir aula</button></nav>
    <ErrorBoundary resetKey={page} home={<button type="button" onClick={() => setPage('home')}>Voltar ao início</button>}>
      <Suspense fallback={<p role="status">Carregando aula…</p>}>
        {page === 'home' ? <h1>Início de teste</h1> : <Page />}
      </Suspense>
    </ErrorBoundary>
  </>
}
createRoot(document.getElementById('root')!).render(<ErrorBoundary><Harness /></ErrorBoundary>)
