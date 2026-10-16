import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

export function routeLabel(pathname: string): string {
  if (pathname === '/inicio') return 'Hoje'
  if (pathname === '/cursos') return 'Cursos'
  if (pathname === '/revisar') return 'Revisão'
  if (pathname === '/caderno') return 'Caderno'
  if (pathname === '/meus-dados') return 'Meus dados'
  if (pathname.endsWith('/conclusao')) return 'Conclusão do curso'
  if (pathname.endsWith('/checkpoint')) return 'Checkpoint da unidade'
  if (pathname.endsWith('/avaliacao')) return 'Avaliação da unidade'

  const lesson = pathname.match(/\/aulas\/(\d+)/)?.[1]
  if (lesson && pathname.includes('/exercicios')) return `Exercícios da Aula ${lesson}`
  if (lesson && pathname.includes('/estudar')) return `Estudo da Aula ${lesson}`
  if (lesson) return `Aula ${lesson}`
  if (pathname.includes('/unidades/')) return 'Mapa da unidade'
  if (pathname.startsWith('/cursos/')) return 'Mapa do curso'
  return 'Página não encontrada'
}

export function RouteStatus() {
  const { pathname } = useLocation()
  const label = routeLabel(pathname)

  useEffect(() => {
    document.title = `${label} | Aulas de Inglês`
    const frame = requestAnimationFrame(() => document.querySelector<HTMLElement>('#main-content')?.focus())
    return () => cancelAnimationFrame(frame)
  }, [label])

  return (
    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {label} carregada.
    </p>
  )
}
