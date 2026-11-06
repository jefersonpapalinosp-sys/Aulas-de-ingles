import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SessaoProvider, useSessao } from '../src/api/auth'
import { PersonalDataPage } from '../src/pages/PersonalDataPage'
import '../src/styles.css'

// Sessão, transporte e formulário reais; o servidor do harness bloqueia a API.
// Somente o Playwright responde às rotas com uma conta sintética.
function Harness() {
  const { usuario, carregando, aviso } = useSessao()
  return <main>
    <output aria-label="Sessão">{usuario?.display_name ?? 'sem sessão'}</output>
    {aviso && <p role="status">{aviso}</p>}
    {!carregando && usuario && <PersonalDataPage />}
  </main>
}
createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><SessaoProvider><Harness /></SessaoProvider></MemoryRouter>
  </QueryClientProvider>,
)
