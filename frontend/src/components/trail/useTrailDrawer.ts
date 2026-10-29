import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute('hidden'))
}

/** A gaveta da trilha no celular: foco preso dentro, Esc fecha, foco devolvido.
 *
 * O ciclo de Tab é feito à mão porque `showModal` não existe em todos os
 * navegadores que o projeto atende — quando ele falta, o `dialog` abre por
 * atributo e nada prende o foco. Sair da gaveta com Tab e continuar navegando
 * a página por trás deixaria quem usa teclado perdido.
 */
export function useTrailDrawer() {
  const [open, setOpen] = useState(false)
  const drawerRef = useRef<HTMLDialogElement>(null)
  const openButtonRef = useRef<HTMLButtonElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    const dialog = drawerRef.current
    if (dialog && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal()
      else dialog.setAttribute('open', '')
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    requestAnimationFrame(() => searchRef.current?.focus())
    return () => { document.body.style.overflow = previousOverflow }
  }, [open])

  /** `returnFocus` é falso quando a gaveta fecha por navegação: o foco vai
   * para a página nova, e não de volta para o botão que a abriu. */
  function close(returnFocus = true) {
    setOpen(false)
    if (returnFocus) requestAnimationFrame(() => openButtonRef.current?.focus())
  }

  function onKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
      return
    }
    if (event.key !== 'Tab' || !drawerRef.current) return
    const focusable = focusableElements(drawerRef.current)
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (!first || !last) return
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return { open, drawerRef, openButtonRef, searchRef, onKeyDown,
    openDrawer: () => setOpen(true), close }
}
