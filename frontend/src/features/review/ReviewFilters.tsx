import type { CourseCurriculum, CourseSummary, ReviewItemType } from '../../api/client'
import { TYPE_LABELS } from './reviewLabels'

/** Escopo e filtros da fila de revisão.
 *
 * Escopo (curso e unidade) vai na URL, porque é compartilhável e sobrevive a um
 * recarregamento; tipo, competência e duração são da sessão de revisão. Trocar
 * qualquer filtro desvira a carta: a resposta visível era de outro item.
 */
export function ReviewFilters({
  courseSlug, unitSlug, courses, units, itemType, skill, maxMinutes, hasActivityFilters,
  onScope, onItemType, onSkill, onMaxMinutes, onClear,
}: {
  courseSlug: string
  unitSlug: string
  courses: CourseSummary[]
  units: CourseCurriculum['units']
  itemType: ReviewItemType | ''
  skill: string
  maxMinutes: number | ''
  hasActivityFilters: boolean
  onScope: (courseSlug: string, unitSlug?: string) => void
  onItemType: (value: ReviewItemType | '') => void
  onSkill: (value: string) => void
  onMaxMinutes: (value: number | '') => void
  onClear: () => void
}) {
  return (
    <>
      <div className="review-filters" aria-label="Escopo da revisão">
        <label>
          Curso
          <select value={courseSlug} onChange={(event) => onScope(event.target.value)}>
            {courses.map((course) => (
              <option key={course.slug} value={course.slug}>{course.title}</option>
            ))}
          </select>
        </label>
        <label>
          Unidade
          <select value={unitSlug} onChange={(event) => onScope(courseSlug, event.target.value)}>
            <option value="">Todas as unidades</option>
            {units.map((unit) => (
              <option key={unit.slug} value={unit.slug}>{unit.title}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="review-filters" aria-label="Filtros da revisão">
        <label>
          Tipo
          <select
            value={itemType}
            onChange={(event) => onItemType(event.target.value as ReviewItemType | '')}
          >
            <option value="">Todos</option>
            {Object.entries(TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          Competência
          <select value={skill} onChange={(event) => onSkill(event.target.value)}>
            <option value="">Todas</option>
            <option value="vocabulary">Vocabulário</option>
            <option value="grammar">Gramática</option>
            <option value="listening">Listening</option>
            <option value="writing">Escrita</option>
            <option value="speaking">Fala</option>
          </select>
        </label>
        <label>
          Duração
          <select
            value={maxMinutes}
            onChange={(event) => onMaxMinutes(event.target.value ? Number(event.target.value) : '')}
          >
            <option value="">Qualquer</option>
            <option value="2">Até 2 min</option>
            <option value="5">Até 5 min</option>
            <option value="10">Até 10 min</option>
          </select>
        </label>
        {hasActivityFilters && (
          <button type="button" onClick={onClear}>Limpar filtros</button>
        )}
      </div>
    </>
  )
}
