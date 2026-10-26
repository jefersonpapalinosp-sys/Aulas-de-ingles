import { Link } from 'react-router-dom'
import { lessonPath } from '../../routing/courseRoutes'
import {
  ACTIVITY_TYPE_LABELS,
  PRACTICE_MODE_LABELS,
  PRACTICE_OBJECTIVE_LABELS,
  SKILL_LABELS,
  type PracticeActivityType,
  type PracticeFilters,
  type PracticeMode,
  type PracticeObjective,
  type PracticeSkill,
} from './types'

export type PracticeOptions = {
  activityTypes: PracticeActivityType[]
  skills: PracticeSkill[]
  objectives: PracticeObjective[]
}

function modeDescription(mode: PracticeMode): string {
  if (mode === 'quick') return 'Até cinco questões em ordem estável. Orçamento sugerido: 10 min; cerca de 2 min por item, sem cronômetro.'
  if (mode === 'mistakes') return 'Uma nova sessão apenas com os itens frágeis desta tentativa.'
  return 'Todos os itens do recorte, com dicas progressivas e explicação.'
}

function activityLabel(value: string): string {
  return ACTIVITY_TYPE_LABELS[value] ?? value.replaceAll('_', ' ')
}

/** A aula existe, mas o pack autoral ainda não foi publicado. */
export function PracticeEmpty({ courseSlug, lessonNumber }: { courseSlug: string; lessonNumber: number }) {
  return (
    <div className="practice-state empty">
      <p className="study-kicker">Em preparação</p>
      <h2>Esta aula ainda não possui exercícios</h2>
      <p>Você pode estudar a teoria agora e voltar quando o pack autoral for publicado.</p>
      <Link className="btn ghost" to={lessonPath(courseSlug, lessonNumber)}>
        Voltar à aula
      </Link>
    </div>
  )
}

/** Escolha do modo e do recorte antes de abrir a sessão.
 *
 * O botão de começar depende de rede: uma sessão nasce na conta. Uma sessão já
 * aberta continua respondível offline, e a nota ao lado diz isso.
 */
export function PracticeIntro({
  lessonNumber, variant, lockFilters, mode, onMode, filters, onFilters, options,
  total, filteredTotal, filtering, filterError, online, starting, startError, onStart,
}: {
  lessonNumber: number
  variant: 'full' | 'embedded'
  lockFilters: boolean
  mode: PracticeMode
  onMode: (mode: PracticeMode) => void
  filters: PracticeFilters
  onFilters: (update: (current: PracticeFilters) => PracticeFilters) => void
  options: PracticeOptions
  total: number
  filteredTotal: number
  filtering: boolean
  filterError: boolean
  online: boolean
  starting: boolean
  startError: string
  onStart: () => void
}) {
  return (
    <section className={`practice-intro ${variant}`} aria-labelledby="practice-intro-title">
      <p className="study-kicker">Laboratório da Aula {lessonNumber}</p>
      <h2 id="practice-intro-title">Escolha como praticar</h2>
      <p className="study-copy">
        Uma questão por vez. A correção objetiva compara sua resposta com o gabarito
        autoral deste exercício; não é uma avaliação geral do seu inglês. Não há ranking
        nem tempo obrigatório.
      </p>

      <fieldset className="practice-modes">
        <legend>Modo da sessão</legend>
        {(['guided', 'quick', 'mistakes'] as const).map((itemMode) => (
          <label key={itemMode}>
            <input
              type="radio"
              name={`practice-mode-${lessonNumber}`}
              value={itemMode}
              checked={mode === itemMode}
              disabled={itemMode === 'mistakes'}
              onChange={() => onMode(itemMode)}
            />
            <span>
              <strong>{PRACTICE_MODE_LABELS[itemMode]}</strong>
              <small>{modeDescription(itemMode)}</small>
            </span>
          </label>
        ))}
      </fieldset>

      {!lockFilters && (
        <div className="practice-filters" aria-label="Filtros de exercícios">
          <label>
            Modalidade
            <select
              value={filters.activityType ?? ''}
              onChange={(event) => onFilters((current) => ({
                ...current,
                activityType: (event.target.value || undefined) as PracticeActivityType | undefined,
              }))}
            >
              <option value="">Todas</option>
              {options.activityTypes.map((value) => (
                <option value={value} key={value}>{activityLabel(value)}</option>
              ))}
            </select>
          </label>
          <label>
            Competência
            <select
              value={filters.skill ?? ''}
              onChange={(event) => onFilters((current) => ({
                ...current,
                skill: (event.target.value || undefined) as PracticeSkill | undefined,
              }))}
            >
              <option value="">Todas</option>
              {options.skills.map((value) => (
                <option value={value} key={value}>{SKILL_LABELS[value] ?? value}</option>
              ))}
            </select>
          </label>
          <label>
            Objetivo
            <select
              value={filters.objective ?? ''}
              onChange={(event) => onFilters((current) => ({
                ...current,
                objective: (event.target.value || undefined) as PracticeObjective | undefined,
              }))}
            >
              <option value="">Todos</option>
              {options.objectives.map((value) => (
                <option value={value} key={value}>{PRACTICE_OBJECTIVE_LABELS[value]}</option>
              ))}
            </select>
          </label>
        </div>
      )}

      <p className="practice-count" role="status" aria-live="polite">
        {filtering ? 'Atualizando o recorte…' : `${filteredTotal} de ${total} atividades disponíveis neste recorte.`}
      </p>
      {filterError && <p className="erro" role="alert">Não foi possível aplicar os filtros. Tente novamente.</p>}
      {!filtering && !filterError && filteredTotal === 0 && (
        <p className="practice-filter-empty">
          Nenhuma atividade combina com estes filtros. Escolha outro recorte.
        </p>
      )}
      {!online && (
        <p className="practice-offline-note" role="status">
          Conecte-se para iniciar uma sessão. Tentativas de uma sessão já aberta continuam
          disponíveis offline.
        </p>
      )}
      <button
        type="button"
        className="btn practice-start"
        disabled={starting || filtering || filteredTotal === 0 || !online}
        onClick={onStart}
      >
        {starting ? 'Iniciando…' : `Começar ${PRACTICE_MODE_LABELS[mode]}`}
      </button>
      {startError && <p className="erro" role="alert">{startError}</p>}
    </section>
  )
}
