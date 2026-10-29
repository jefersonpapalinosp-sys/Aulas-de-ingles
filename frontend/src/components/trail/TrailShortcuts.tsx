import { NavLink } from 'react-router-dom'
import {
  assessmentPath,
  notebookPath,
  reviewPath,
  todayPath,
  unitPath,
} from '../../routing/courseRoutes'

/** Atalhos da trilha.
 *
 * Avaliação e mapa só aparecem quando há uma unidade publicada no escopo: um
 * atalho para unidade em preparação levaria o aluno a uma tela vazia.
 */
export function TrailShortcuts({
  courseSlug, scopeUnitSlug, reviewDue, onNavigate,
}: {
  courseSlug: string
  scopeUnitSlug?: string
  reviewDue?: number
  onNavigate?: () => void
}) {
  return (
    <nav className="trail-utilities" aria-label="Atalhos">
      <NavLink to={todayPath(courseSlug)} onClick={onNavigate}>Hoje</NavLink>
      <NavLink to="/cursos" onClick={onNavigate}>Cursos</NavLink>
      <NavLink to={reviewPath(courseSlug, scopeUnitSlug)} onClick={onNavigate}>
        Revisar
        {Boolean(reviewDue) && <span className="badge">{reviewDue}</span>}
      </NavLink>
      <NavLink to={notebookPath(courseSlug, scopeUnitSlug)} onClick={onNavigate}>Caderno</NavLink>
      <NavLink to="/meus-dados" onClick={onNavigate}>Meus dados</NavLink>
      {scopeUnitSlug && (
        <NavLink to={assessmentPath(courseSlug, scopeUnitSlug)} onClick={onNavigate}>
          Avaliação
        </NavLink>
      )}
      {scopeUnitSlug && (
        <NavLink to={unitPath(courseSlug, scopeUnitSlug)} onClick={onNavigate}>
          Mapa da unidade
        </NavLink>
      )}
    </nav>
  )
}
