import { NavLink } from 'react-router-dom'
import type { LessonSummary } from '../api/client'

export function LessonRail({ aulas }: { aulas: LessonSummary[] }) {
  return (
    <nav className="rail" aria-label="Aulas do bloco">
      <div className="rail-head">
        <p className="brand">VOA · Let's Learn English · Level 1</p>
        <h2>Bloco 31–40</h2>
      </div>

      <p className="rail-group">Visão geral</p>
      <NavLink to="/" end className="flat">
        Mapa do bloco
      </NavLink>

      <p className="rail-group">Aulas</p>
      {aulas.map((a) => (
        <NavLink key={a.number} to={`/aulas/${a.number}`} className="nav-item">
          <span className="nav-n">{a.number}</span>
          <span className="nav-t">
            <b>{a.title}</b>
            <span>{a.grammar_tag}</span>
          </span>
        </NavLink>
      ))}

      <p className="rail-group">Fechamento</p>
      <NavLink to="/prova" className="flat">
        Prova do bloco
      </NavLink>
    </nav>
  )
}
