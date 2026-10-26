import { Link } from 'react-router-dom'
import type { CourseCompletion } from '../../api/client'
import { SkillEvidenceMeta } from '../skills/SkillEvidenceMeta'
import { skillStatusLabel } from './completionLabels'

export function IncompleteWork({ data }: { data: CourseCompletion }) {
  const { incomplete_units: incompleteUnits, checkpoints } = data

  return (
    <div className="completion-two-column">
      <section className="completion-panel" aria-labelledby="incomplete-units-title">
        <p className="eyebrow">Aulas</p>
        <h2 id="incomplete-units-title">Unidades para continuar</h2>
        {incompleteUnits.length === 0 ? (
          <p className="completion-positive" role="status">
            Todas as unidades publicadas têm suas aulas concluídas.
          </p>
        ) : (
          <ul className="completion-link-list">
            {incompleteUnits.map((unit) => (
              <li key={unit.slug}>
                <Link to={unit.href}>
                  <strong>{unit.title}</strong>
                  <span>
                    {unit.completed_lessons}/{unit.published_lessons} concluídas ·{' '}
                    {unit.viewed_lessons} vistas
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <p className="completion-preserved-access">
          Estas unidades continuam acessíveis para estudo e revisão.
        </p>
      </section>

      <section className="completion-panel" aria-labelledby="pending-checkpoints-title">
        <p className="eyebrow">Revisões do recorte</p>
        <h2 id="pending-checkpoints-title">Checkpoints atuais</h2>
        <p className="completion-panel-summary">
          {checkpoints.current_completed} de {checkpoints.published} realizados na versão
          atual.
        </p>
        {checkpoints.pending.length > 0 ? (
          <ul className="completion-link-list">
            {checkpoints.pending.map((checkpoint) => (
              <li key={`${checkpoint.unit_slug}-${checkpoint.content_version}`}>
                <Link to={checkpoint.href}>
                  <strong>{checkpoint.title}</strong>
                  <span>Versão atual {checkpoint.content_version} · fazer checkpoint</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : checkpoints.published > 0 ? (
          <p className="completion-positive" role="status">
            Todos os checkpoints publicados foram realizados na versão atual.
          </p>
        ) : (
          <p className="muted">Ainda não há checkpoints publicados neste curso.</p>
        )}
      </section>
    </div>
  )
}

export function SkillsEvidence({ data }: { data: CourseCompletion }) {
  return (
    <section className="completion-skills" aria-labelledby="completion-skills-title">
      <p className="eyebrow">Evidências de prática</p>
      <h2 id="completion-skills-title">Competências observadas</h2>
      <p className="completion-section-intro">
        Competência não é calculada pelas aulas vistas. Ela resume tentativas registradas
        em exercícios, práticas de fala e feedbacks de escrita; checkpoints aparecem
        separadamente. São necessárias pelo menos três amostras para mostrar uma tendência.
      </p>

      {data.skills.length === 0 ? (
        <p className="completion-empty-copy" role="status">
          Ainda não há evidências de competência para resumir.
        </p>
      ) : (
        <ul className="completion-skill-list">
          {data.skills.map((skill) => {
            const insufficient = skill.samples < 3 || skill.score_percent === null
            return (
              <li key={skill.skill}>
                <div>
                  <strong>{skill.label}</strong>
                  <span>{skill.samples} {skill.samples === 1 ? 'evidência' : 'evidências'}</span>
                </div>
                {insufficient ? (
                  <span className="completion-skill-state insufficient">
                    Dados insuficientes ({skill.samples}/3)
                  </span>
                ) : (
                  <span className={`completion-skill-state ${skill.status}`}>
                    {skillStatusLabel(skill.status)} · {skill.score_percent}%
                  </span>
                )}
                {skill.fragile_topics.length > 0 && (
                  <p>Pontos para revisar: {skill.fragile_topics.join(', ')}.</p>
                )}
                <SkillEvidenceMeta skill={skill} />
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
