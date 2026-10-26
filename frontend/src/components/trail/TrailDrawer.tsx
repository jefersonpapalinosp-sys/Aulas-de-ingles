import type { KeyboardEvent, ReactNode, RefObject } from 'react'

/** Casca da gaveta: barra do celular e o `dialog` com a trilha dentro. */
export function TrailDrawer({
  label, open, drawerRef, openButtonRef, onOpen, onClose, onKeyDown, children,
}: {
  label: string
  open: boolean
  drawerRef: RefObject<HTMLDialogElement | null>
  openButtonRef: RefObject<HTMLButtonElement | null>
  onOpen: () => void
  onClose: (returnFocus?: boolean) => void
  onKeyDown: (event: KeyboardEvent<HTMLDialogElement>) => void
  children: ReactNode
}) {
  return (
    <>
      <div className="mobile-trail-bar">
        <button
          ref={openButtonRef}
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={onOpen}
        >
          <span>
            <small>Trilha atual</small>
            <strong>{label}</strong>
          </span>
          <span aria-hidden="true">☰</span>
          <span className="sr-only">Abrir trilha de aulas</span>
        </button>
      </div>

      {open && (
        <dialog
          ref={drawerRef}
          className="trail-drawer-backdrop"
          aria-labelledby="trail-drawer-title"
          onClose={() => onClose()}
          onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}
          onKeyDown={onKeyDown}
        >
          <div className="trail-drawer">
            <div className="trail-drawer-titlebar">
              <h2 id="trail-drawer-title">Trilha de estudo</h2>
              <button type="button" onClick={() => onClose()} aria-label="Fechar trilha">×</button>
            </div>
            {children}
          </div>
        </dialog>
      )}
    </>
  )
}
