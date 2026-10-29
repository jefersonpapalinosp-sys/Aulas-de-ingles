import type { Ref } from 'react'
import type { Exercise } from '../../api/client'

/** Um componente por `activity_type`.
 *
 * O despachante abaixo é a única parte que conhece os tipos. Antes era uma
 * escada de ternários dentro do formulário, e cada atividade nova engordava o
 * mesmo arquivo — que é o que o FE-46 vem desfazer.
 */

type Comum = { disabled: boolean; description: string; invalid: boolean }

export function ClassificationInput({
  exercicio, items, categories, assignments, disabled, description, invalid, firstRef, onAssign,
}: Comum & {
  exercicio: Exercise
  items: string[]
  categories: string[]
  assignments: Record<string, string>
  firstRef?: Ref<HTMLSelectElement>
  onAssign: (item: string, category: string) => void
}) {
  return (
    <fieldset aria-describedby={description} aria-invalid={invalid} className="classification-activity">
      <legend>Classifique cada item</legend>
      <div className="classification-grid">
        {items.map((item, index) => {
          const selectId = `classification-${exercicio.id}-${index}`
          return (
            <label htmlFor={selectId} key={item}>
              <span>{item}</span>
              <select
                aria-describedby={description}
                aria-invalid={invalid}
                id={selectId}
                ref={index === 0 ? firstRef : undefined}
                value={assignments[item] ?? ''}
                disabled={disabled}
                onChange={(event) => onAssign(item, event.target.value)}
              >
                <option value="">Selecione uma categoria</option>
                {categories.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

export function ReorderInput({
  options, ordem, disabled, description, invalid, firstRef, onChange,
}: Comum & {
  options: string[]
  ordem: string[]
  firstRef?: Ref<HTMLButtonElement>
  onChange: (next: string[]) => void
}) {
  return (
    <fieldset aria-describedby={description} aria-invalid={invalid} className="reorder-activity">
      <legend>Monte a frase</legend>
      <div className="reorder-answer" aria-label="Frase montada">
        {ordem.length === 0 ? (
          <span>Escolha as palavras na ordem correta</span>
        ) : (
          ordem.map((word, index) => (
            <button
              type="button"
              key={`${word}-${index}`}
              aria-label={`Remover ${word}`}
              disabled={disabled}
              onClick={() => onChange(ordem.filter((_, itemIndex) => itemIndex !== index))}
            >
              {word}
            </button>
          ))
        )}
      </div>
      <div className="reorder-options" aria-label="Palavras disponíveis">
        {options.map((word, index) => (
          <button
            type="button"
            key={`${word}-${index}`}
            ref={index === 0 ? firstRef : undefined}
            disabled={disabled || ordem.includes(word)}
            aria-label={`Adicionar ${word}`}
            onClick={() => onChange([...ordem, word])}
          >
            {word}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

export function ChoiceInput({
  exercicio, options, value, disabled, description, invalid, firstRef, onChange,
}: Comum & {
  exercicio: Exercise
  options: string[]
  value: string
  firstRef?: Ref<HTMLInputElement>
  onChange: (value: string) => void
}) {
  return (
    <fieldset aria-describedby={description} aria-invalid={invalid} className="choice-options">
      <legend>Escolha uma resposta</legend>
      {options.map((option, index) => (
        <label key={option}>
          <input
            ref={index === 0 ? firstRef : undefined}
            aria-describedby={description}
            type="radio"
            name={`exercise-${exercicio.id}`}
            value={option}
            checked={value === option}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
          />
          <span>{option}</span>
        </label>
      ))}
    </fieldset>
  )
}

export function TextAnswerInput({
  numero, value, disabled, description, invalid, inputRef, onChange,
}: Comum & {
  numero: number
  value: string
  inputRef?: Ref<HTMLInputElement>
  onChange: (value: string) => void
}) {
  return (
    <input
      ref={inputRef}
      aria-describedby={description}
      aria-invalid={invalid}
      type="text"
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      placeholder="sua resposta"
      aria-label={`Resposta do exercício ${numero}`}
      autoComplete="off"
      spellCheck={false}
    />
  )
}
