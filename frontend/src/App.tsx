import { Route, Routes } from 'react-router-dom'
import { useSessao } from './api/auth'
import { useLessons } from './api/queries'
import { LessonRail } from './components/LessonRail'
import { LessonPage } from './pages/LessonPage'
import { LoginPage } from './pages/LoginPage'
import { MapPage } from './pages/MapPage'
import { ReviewPage } from './pages/ReviewPage'
import { TestPage } from './pages/TestPage'

export default function App() {
  const { usuario, carregando } = useSessao()
  // A trilha precisa da lista em toda rota; o React Query serve do cache.
  const { data: aulas } = useLessons()

  // Enquanto o /refresh não responde, mostrar o login faria a tela piscar
  // para quem já tem sessão válida no cookie.
  if (carregando) return <p className="booting">Carregando…</p>
  if (!usuario) return <LoginPage />

  return (
    <div className="shell">
      <LessonRail aulas={aulas ?? []} />
      <main>
        <Routes>
          <Route path="/" element={<MapPage />} />
          <Route path="/aulas/:numero" element={<LessonPage />} />
          <Route path="/revisar" element={<ReviewPage />} />
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
  )
}
