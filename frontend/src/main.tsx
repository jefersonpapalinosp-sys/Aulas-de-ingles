import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { SessaoProvider } from './api/auth'
import './styles.css'

const root = document.getElementById('root')
if (!root) throw new Error('#root não encontrado no index.html')

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Conteúdo de aula só muda quando roda o seed — não vale revalidar a cada foco.
      staleTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessaoProvider>
          <App />
        </SessaoProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
