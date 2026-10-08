import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { LegacyLessonRedirect } from '../App'
import {
  canonicalizeLegacyHref,
  lessonPath,
  practicePath,
  studyPath,
} from './courseRoutes'

function LocationProbe() {
  const location = useLocation()
  return <output>{`${location.pathname}${location.search}${location.hash}`}</output>
}

describe('rotas de curso', () => {
  it('distingue aulas com o mesmo número em cursos diferentes', () => {
    expect(lessonPath('voa-level-1', 1)).toBe('/cursos/voa-level-1/aulas/1')
    expect(lessonPath('voa-level-2', 1)).toBe('/cursos/voa-level-2/aulas/1')
    expect(studyPath('voa-level-2', 1, 'assistir')).toBe(
      '/cursos/voa-level-2/aulas/1/estudar/assistir',
    )
    expect(practicePath('voa-level-2', 1)).toBe(
      '/cursos/voa-level-2/aulas/1/exercicios',
    )
  })

  it('normaliza recomendações legadas sem alterar links não relacionados', () => {
    expect(canonicalizeLegacyHref('/aulas/31/estudar/revisar?origem=hoje')).toBe(
      '/cursos/voa-level-1/aulas/31/estudar/revisar?origem=hoje',
    )
    expect(canonicalizeLegacyHref('/revisar')).toBe('/revisar')
  })

  it.each(['preparar', 'assistir', 'estudar', 'praticar', 'revisar'])(
    'redireciona a etapa legada %s e preserva busca e hash',
    async (step) => {
      render(
        <MemoryRouter initialEntries={[`/aulas/31/estudar/${step}?from=saved#top`]}>
          <Routes>
            <Route
              path="/aulas/:numero/estudar/:etapa"
              element={<LegacyLessonRedirect study />}
            />
            <Route path="*" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>,
      )
      expect(
        await screen.findByText(
          `/cursos/voa-level-1/aulas/31/estudar/${step}?from=saved#top`,
        ),
      ).toBeInTheDocument()
    },
  )
})
