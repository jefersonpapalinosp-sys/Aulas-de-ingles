import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { setAccessToken, setSessionUser } from '../src/api/client'
import DialogueWorkspace from '../src/features/dialogue/DialogueWorkspace'
import { lessonFixture } from '../src/features/dialogue/dialogueFixtures'
import '../src/styles.css'

// O servidor desse harness bloqueia /api; somente Playwright responde com dados sintéticos.
setAccessToken('synthetic-test-only')
setSessionUser(3)
createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <main><h1>Conversa de teste</h1><DialogueWorkspace lesson={lessonFixture} userId={3} /></main>
  </QueryClientProvider>,
)
