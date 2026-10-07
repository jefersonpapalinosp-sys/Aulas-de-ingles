import { Route, Routes } from 'react-router-dom'
import { useLessons } from './api/queries'
import { LessonRail } from './components/LessonRail'
import { LessonPage } from './pages/LessonPage'
import { MapPage } from './pages/MapPage'
import { TestPage } from './pages/TestPage'

export default function App() {
  // A trilha precisa da lista em toda rota; o React Query serve do cache.
  const { data: aulas } = useLessons()

  return (
    <div className="shell">
      <LessonRail aulas={aulas ?? []} />
      <main>
        <Routes>
          <Route path="/" element={<MapPage />} />
          <Route path="/aulas/:numero" element={<LessonPage />} />
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
