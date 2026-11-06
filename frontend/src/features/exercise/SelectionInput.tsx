import type { Ref } from 'react'

/** Identificadores estáveis; o componente não conhece gabaritos nem cursos. */
export function SelectionInput({ name, legend, options, selected, multiple = false,
  disabled, description, invalid = false, firstRef, onChange }: {
  name: string; legend: string; options: { id: string; label: string }[]
  selected: string[]; multiple?: boolean; disabled: boolean; description: string
  invalid?: boolean; firstRef?: Ref<HTMLInputElement>; onChange: (ids: string[]) => void
}) {
  return <fieldset aria-describedby={description} aria-invalid={invalid} className="choice-options">
    <legend>{legend}</legend>
    {options.map((option, index) => <label key={option.id}>
      <input ref={index === 0 ? firstRef : undefined} aria-describedby={description}
        type={multiple ? 'checkbox' : 'radio'} name={name} value={option.id}
        checked={selected.includes(option.id)} disabled={disabled}
        onChange={() => onChange(multiple
          ? selected.includes(option.id) ? selected.filter(id => id !== option.id) : [...selected, option.id]
          : [option.id])} />
      <span>{option.label}</span>
    </label>)}
  </fieldset>
}
