import { NavLink } from 'react-router-dom'
import { useSessao } from '../api/auth'
import type { LessonSummary } from '../api/client'
import { useMarcarEstudada, useProgress } from '../api/progress'

export function LessonRail({ aulas }: { aulas: LessonSummary[] }) {
  const { usuario, sair } = useSessao()
  const { data: progresso } = useProgress()
  const marcar = useMarcarEstudada()

  const estudadas = new Set(
    progresso?.lessons.filter((l) => l.studied).map((l) => l.lesson_number) ?? [],
  )
  const total = progresso?.total_lessons ?? aulas.length

  return (
    <nav className="rail" aria-label="Aulas do bloco">
      <div className="rail-head">
        <p className="brand">VOA · Let's Learn English · Level 1</p>
        <h2>Bloco 31–40</h2>
        {usuario && (
          <p className="quem">
            {usuario.display_name}
            <button type="button" onClick={() => void sair()}>
              sair
            </button>
          </p>
        )}

        <div className="prog">
          <div className="prog-top">
            <span>Estudadas</span>
            <span>
              {estudadas.size}/{total}
            </span>
          </div>
          <div className="prog-bar">
            <div
              className="prog-fill"
              style={{ width: total ? `${(estudadas.size / total) * 100}%` : '0%' }}
            />
          </div>
        </div>
      </div>

      <p className="rail-group">Visão geral</p>
      <NavLink to="/" end className="flat">
        Hoje e mapa
      </NavLink>

      <p className="rail-group">Aulas</p>
      {aulas.map((a) => (
        <div className="nav-linha" key={a.number}>
          <NavLink to={`/aulas/${a.number}`} className="nav-item">
            <span className="nav-n">{a.number}</span>
            <span className="nav-t">
              <b>{a.title}</b>
              <span>{a.grammar_tag}</span>
            </span>
          </NavLink>
          <button
            type="button"
            className="done"
            aria-pressed={estudadas.has(a.number)}
            aria-label={`Marcar aula ${a.number} como estudada`}
            disabled={marcar.isPending}
            onClick={() =>
              marcar.mutate({ numero: a.number, estudada: !estudadas.has(a.number) })
            }
          >
            ✓
          </button>
        </div>
      ))}

      <p className="rail-group">Fechamento</p>
      <NavLink to="/caderno" className="flat">
        Caderno
      </NavLink>
      <NavLink to="/revisar" className="flat">
        Revisar
        {!!progresso?.review_due && <span className="badge">{progresso.review_due}</span>}
      </NavLink>
      <NavLink to="/prova" className="flat">
        Prova do bloco
      </NavLink>
    </nav>
  )
}
