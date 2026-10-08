import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { useSessao } from './api/auth'
import { LessonRail } from './components/LessonRail'
import { CourseCatalogPage } from './pages/CourseCatalogPage'
import { LessonPage } from './pages/LessonPage'
import { LoginPage } from './pages/LoginPage'
import { MapPage } from './pages/MapPage'
import { NotebookPage } from './pages/NotebookPage'
import { ReviewPage } from './pages/ReviewPage'
import { StudyPage } from './pages/StudyPage'
import { TestPage } from './pages/TestPage'
import { ConnectivityStatus } from './features/offline/ConnectivityStatus'
import { DEFAULT_COURSE_SLUG, lessonPath, studyPath } from './routing/courseRoutes'

export function LegacyLessonRedirect({ study = false }: { study?: boolean }) {
  const { numero, etapa } = useParams()
  const location = useLocation()
  const lessonNumber = Number(numero)
  if (!Number.isInteger(lessonNumber)) return <Navigate to="/cursos" replace />
  const path = study
    ? `${studyPath(DEFAULT_COURSE_SLUG, lessonNumber)}${etapa ? `/${etapa}` : ''}`
    : lessonPath(DEFAULT_COURSE_SLUG, lessonNumber)
  return <Navigate to={`${path}${location.search}${location.hash}`} replace />
}

export default function App() {
  const { usuario, carregando, offline } = useSessao()
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
        <LessonRail />
        <main id="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Navigate to="/inicio" replace />} />
            <Route path="/inicio" element={<MapPage showToday />} />
            <Route path="/cursos" element={<CourseCatalogPage />} />
            <Route path="/cursos/:courseSlug" element={<MapPage />} />
            <Route
              path="/cursos/:courseSlug/unidades/:unitSlug"
              element={<MapPage />}
            />
            <Route path="/cursos/:courseSlug/aulas/:numero" element={<LessonPage />} />
            <Route
              path="/cursos/:courseSlug/aulas/:numero/estudar"
              element={<StudyPage />}
            />
            <Route
              path="/cursos/:courseSlug/aulas/:numero/estudar/:etapa"
              element={<StudyPage />}
            />
            <Route path="/aulas/:numero" element={<LegacyLessonRedirect />} />
            <Route
              path="/aulas/:numero/estudar"
              element={<LegacyLessonRedirect study />}
            />
            <Route
              path="/aulas/:numero/estudar/:etapa"
              element={<LegacyLessonRedirect study />}
            />
            <Route path="/revisar" element={<ReviewPage />} />
            <Route path="/caderno" element={<NotebookPage />} />
            <Route path="/prova" element={<TestPage />} />
            <Route
              path="*"
              element={
                <>
                  <h1>Página não encontrada</h1>
                  <p className="lead">Use a trilha para voltar ao catálogo do curso.</p>
                </>
              }
            />
          </Routes>
        </main>
      </div>
    </>
  )
}
