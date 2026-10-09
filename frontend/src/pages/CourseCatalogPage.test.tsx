import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { CourseCatalogPage } from './CourseCatalogPage'

vi.mock('../api/queries', () => ({
  useCourses: () => ({
    data: [
      {
        id: 1,
        slug: 'voa-level-1',
        title: "Let's Learn English — Level 1",
        level: 'Level 1',
        proficiency_label: 'Iniciante',
        provider: 'VOA Learning English',
        source_url: 'https://example.com/level-1',
        position: 1,
        status: 'published',
        total_lessons: 52,
        published_lessons: 10,
      },
      {
        id: 2,
        slug: 'voa-level-2',
        title: "Let's Learn English — Level 2",
        level: 'Level 2',
        proficiency_label: 'Intermediário',
        provider: 'VOA Learning English',
        source_url: 'https://example.com/level-2',
        position: 2,
        status: 'published',
        total_lessons: 30,
        published_lessons: 5,
      },
    ],
    isPending: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

describe('CourseCatalogPage', () => {
  it('apresenta os dois cursos publicados e o recorte disponível de cada um', () => {
    render(<CourseCatalogPage />, { wrapper: MemoryRouter })

    expect(screen.getByRole('heading', { name: 'Cursos de inglês' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Level 1/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Level 2/ })).toBeInTheDocument()
    expect(screen.getAllByText('Publicado')).toHaveLength(2)
    expect(screen.getByText('5/30')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Ver unidades' }).at(0)).toHaveAttribute(
      'href',
      '/cursos/voa-level-1',
    )
  })
})
