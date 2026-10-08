import { Route, Routes } from 'react-router-dom'
import { useSessao } from './api/auth'
import { useLessons } from './api/queries'
import { LessonRail } from './components/LessonRail'
import { LessonPage } from './pages/LessonPage'
import { LoginPage } from './pages/LoginPage'
import { MapPage } from './pages/MapPage'
import { NotebookPage } from './pages/NotebookPage'
import { ReviewPage } from './pages/ReviewPage'
import { StudyPage } from './pages/StudyPage'
import { TestPage } from './pages/TestPage'
import { ConnectivityStatus } from './features/offline/ConnectivityStatus'

export default function App() {
  const { usuario, carregando, offline } = useSessao()
  // A trilha precisa da lista em toda rota; o React Query serve do cache.
  const { data: aulas } = useLessons()

  // Enquanto o /refresh não responde, mostrar o login faria a tela piscar
  // para quem já tem sessão válida no cookie.
  if (carregando) return <p className="booting">Carregando…</p>
  if (!usuario) return <LoginPage />

  return (
    <>
      <a className="skip-link" href="#main-content">
        Pular para o conteúdo
      </a>
      <ConnectivityStatus userId={usuario.id} offlineSession={offline} />
      <div className="shell">
        <LessonRail aulas={aulas ?? []} />
        <main id="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<MapPage />} />
            <Route path="/aulas/:numero" element={<LessonPage />} />
            <Route path="/aulas/:numero/estudar" element={<StudyPage />} />
            <Route path="/aulas/:numero/estudar/:etapa" element={<StudyPage />} />
            <Route path="/revisar" element={<ReviewPage />} />
            <Route path="/caderno" element={<NotebookPage />} />
            <Route path="/prova" element={<TestPage />} />
            <Route
              path="*"
              element={
                <>
                  <h1>Página não encontrada</h1>
                  <p className="lead">Use a barra lateral para voltar ao mapa do bloco.</p>
                </>
              }
            />
          </Routes>
        </main>
      </div>
    </>
  )
}
