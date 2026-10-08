import { describe, expect, it } from 'vitest'
import type { CourseCurriculum, LessonSummary } from '../../api/client'
import { adjacentLessons, curriculumLessons, matchesLessonSearch } from './curriculum'

function lesson(number: number, unit: number, position: number): LessonSummary {
  return {
    id: unit * 100 + number,
    course_slug: 'curso-longo',
    unit_slug: `unidade-${unit}`,
    slug: `aula-${number}`,
    position,
    number,
    title: `Lesson ${number}`,
    title_pt: `Aula ${number}`,
    grammar_tag: number === 54 ? 'Present perfect' : 'Grammar',
    focus_points: [],
    story_note: null,
  }
}

function longCurriculum(): CourseCurriculum {
  const lessons = Array.from({ length: 54 }, (_, index) => lesson(index + 1, Math.floor(index / 9) + 1, (index % 9) + 1))
  return {
    course: {
      id: 10,
      slug: 'curso-longo',
      title: 'Curso longo',
      level: 'Level X',
      proficiency_label: 'Teste',
      provider: 'Provider',
      source_url: 'https://example.com',
      position: 1,
      status: 'published',
      total_lessons: 54,
      published_lessons: 54,
    },
    units: Array.from({ length: 6 }, (_, index) => {
      const unitLessons = lessons.slice(index * 9, index * 9 + 9)
      return {
        id: index + 1,
        slug: `unidade-${index + 1}`,
        title: `Unidade ${index + 1}`,
        position: index + 1,
        status: 'published' as const,
        lesson_start: unitLessons[0]!.number,
        lesson_end: unitLessons.at(-1)!.number,
        total_lessons: 9,
        published_lessons: 9,
        lessons: unitLessons,
        review: null,
      }
    }),
  }
}

describe('currículo', () => {
  it('ordena mais de 52 aulas por unidade e posição', () => {
    const lessons = curriculumLessons(longCurriculum())
    expect(lessons).toHaveLength(54)
    expect(lessons.map((item) => item.number)).toEqual(
      Array.from({ length: 54 }, (_, index) => index + 1),
    )
  })

  it('calcula anterior e próxima pela ordem curricular, não pelo número', () => {
    const curriculum = longCurriculum()
    const current = curriculum.units[1]!.lessons[0]!
    expect(adjacentLessons(curriculum, current.id)).toMatchObject({
      previous: { number: 9 },
      next: { number: 11 },
    })
  })

  it('busca por número, título traduzido e tópico', () => {
    const target = longCurriculum().units.at(-1)!.lessons.at(-1)!
    expect(matchesLessonSearch(target, '54')).toBe(true)
    expect(matchesLessonSearch(target, 'aula 54')).toBe(true)
    expect(matchesLessonSearch(target, 'present perfect')).toBe(true)
    expect(matchesLessonSearch(target, 'inexistente')).toBe(false)
  })
})
