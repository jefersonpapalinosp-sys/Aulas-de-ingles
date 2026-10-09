import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { useSessao } from './api/auth'
import { LessonRail } from './components/LessonRail'
import { LoginPage } from './pages/LoginPage'
import { MapPage } from './pages/MapPage'
import { ConnectivityStatus } from './features/offline/ConnectivityStatus'

/**
 * Cada rota pesada vira um chunk próprio. Mapa e login ficam no bundle
 * inicial porque são as duas primeiras telas; o resto só é baixado quando
 * o estudante navega até lá.
 */
const CourseCatalogPage = lazy(() => import('./pages/CourseCatalogPage').then((m) => ({ default: m.CourseCatalogPage })))
const CourseCompletionPage = lazy(() => import('./pages/CourseCompletionPage').then((m) => ({ default: m.CourseCompletionPage })))
const CourseReviewPage = lazy(() => import('./pages/CourseReviewPage').then((m) => ({ default: m.CourseReviewPage })))
const LessonPage = lazy(() => import('./pages/LessonPage').then((m) => ({ default: m.LessonPage })))
const NotebookPage = lazy(() => import('./pages/NotebookPage').then((m) => ({ default: m.NotebookPage })))
const PracticePage = lazy(() => import('./pages/PracticePage').then((m) => ({ default: m.PracticePage })))
const ReviewPage = lazy(() => import('./pages/ReviewPage').then((m) => ({ default: m.ReviewPage })))
const StudyPage = lazy(() => import('./pages/StudyPage').then((m) => ({ default: m.StudyPage })))
const TestPage = lazy(() => import('./pages/TestPage').then((m) => ({ default: m.TestPage })))
import {
  assessmentPath,
  DEFAULT_COURSE_SLUG,
  lessonPath,
  studyPath,
} from './routing/courseRoutes'

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
          <Suspense fallback={<p className="muted" role="status">Carregando…</p>}>
            <Routes>
            <Route path="/" element={<Navigate to="/inicio" replace />} />
            <Route path="/inicio" element={<MapPage showToday />} />
            <Route path="/cursos" element={<CourseCatalogPage />} />
            <Route
              path="/cursos/:courseSlug/conclusao"
              element={<CourseCompletionPage />}
            />
            <Route path="/cursos/:courseSlug" element={<MapPage />} />
            <Route
              path="/cursos/:courseSlug/unidades/:unitSlug"
              element={<MapPage />}
            />
            <Route
              path="/cursos/:courseSlug/unidades/:unitSlug/checkpoint"
              element={<CourseReviewPage />}
            />
            <Route
              path="/cursos/:courseSlug/unidades/:unitSlug/avaliacao"
              element={<TestPage />}
            />
            <Route path="/cursos/:courseSlug/aulas/:numero" element={<LessonPage />} />
            <Route
              path="/cursos/:courseSlug/aulas/:numero/exercicios"
              element={<PracticePage />}
            />
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
            <Route
              path="/prova"
              element={
                <Navigate
                  to={assessmentPath(DEFAULT_COURSE_SLUG, '31-40')}
                  replace
                />
              }
            />
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
          </Suspense>
        </main>
      </div>
    </>
  )
}
