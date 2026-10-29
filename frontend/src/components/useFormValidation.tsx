import { useId, useState, type FormEvent } from 'react'

type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement

/** Expõe a validação nativa ao leitor de tela sem confundir falha de rede com
 * valor inválido. Cada instância tem IDs próprios; editar limpa só seu erro. */
export function useFormValidation() {
  const id = useId()
  const [errors, setErrors] = useState<Record<string, string>>({})
  function clear(name: string) {
    setErrors((current) => {
      if (!current[name]) return current
      const next = { ...current }
      delete next[name]
      return next
    })
  }
  return {
    id,
    reset: () => setErrors({}),
    invalid: (name: string) => Boolean(errors[name]),
    field: (name: string, description?: string, kind: 'field' | 'radio' = 'field') => ({
      'aria-invalid': kind === 'radio' ? undefined : Boolean(errors[name]),
      'aria-describedby': [description, errors[name] ? `${id}-${name}-error` : ''].filter(Boolean).join(' ') || undefined,
      onInvalid: (event: FormEvent<Field>) => {
        const message = event.currentTarget.validationMessage
        setErrors((current) => ({ ...current, [name]: message }))
      },
      onInput: () => clear(name),
    }),
    messages: Object.entries(errors).map(([name, message]) => (
      <p key={name} id={`${id}-${name}-error`} className="erro" role="alert">{message}</p>
    )),
  }
}
