import { useState, type FormEvent } from 'react'
import type { StudyPlan, StudyPlanInput } from '../../api/client'
import { useSaveStudyPlan } from '../../api/dashboard'

/** Dias e minutos que o aluno se compromete a estudar.
 *
 * É plano, não meta imposta: nada no aplicativo bloqueia quem não cumpre. O
 * valor dele é o lembrete e o cálculo do que cabe em "hoje".
 */
const DAYS = [
  ['mon', 'Seg'],
  ['tue', 'Ter'],
  ['wed', 'Qua'],
  ['thu', 'Qui'],
  ['fri', 'Sex'],
  ['sat', 'Sáb'],
  ['sun', 'Dom'],
] as const

export function PlanEditor({ plan }: { plan: StudyPlan }) {
  const save = useSaveStudyPlan()
  const [weeklyMinutes, setWeeklyMinutes] = useState(plan.weekly_minutes)
  const [preferredDays, setPreferredDays] = useState<string[]>(plan.preferred_days)
  const [goal, setGoal] = useState(plan.goal)
  const [timezone, setTimezone] = useState(plan.timezone ?? 'UTC')

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate({
      weekly_minutes: weeklyMinutes,
      preferred_days: preferredDays as StudyPlanInput['preferred_days'],
      goal,
      timezone,
    })
  }

  return (
    <form className="today-plan" onSubmit={submit}>
      <div className="today-section-head">
        <div>
          <p className="eyebrow">Plano semanal</p>
          <h2>Ritmo que cabe na rotina</h2>
        </div>
        <button className="btn ghost" disabled={save.isPending || preferredDays.length === 0}>
          {save.isPending ? 'Salvando…' : 'Salvar plano'}
        </button>
      </div>
      <label>
        Meta
        <input
          type="text"
          value={goal}
          maxLength={200}
          required
          onChange={(event) => setGoal(event.target.value)}
        />
      </label>
      <label>
        Minutos por semana
        <input
          className="today-minutes"
          type="number"
          min={30}
          max={600}
          step={15}
          value={weeklyMinutes}
          onChange={(event) => setWeeklyMinutes(Number(event.target.value))}
        />
      </label>
      <label>
        Fuso horário da semana (IANA)
        <input value={timezone} required maxLength={80} list="study-timezones"
          onChange={(event) => setTimezone(event.target.value)} />
        <datalist id="study-timezones"><option value="UTC" /><option value="America/Sao_Paulo" /></datalist>
      </label>
      <fieldset>
        <legend>Dias preferidos</legend>
        <div className="today-days">
          {DAYS.map(([value, label]) => (
            <label key={value}>
              <input
                type="checkbox"
                checked={preferredDays.includes(value)}
                onChange={(event) =>
                  setPreferredDays((current) =>
                    event.target.checked
                      ? [...current, value]
                      : current.filter((day) => day !== value),
                  )
                }
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      {save.isSuccess && (
        <p className="today-save ok" role="status">
          Plano salvo.
        </p>
      )}
      {save.isError && (
        <p className="today-save erro" role="alert">
          Não foi possível salvar.
        </p>
      )}
    </form>
  )
}
