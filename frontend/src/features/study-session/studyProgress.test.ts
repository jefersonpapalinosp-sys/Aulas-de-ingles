import { afterEach, describe, expect, it } from 'vitest'
import {
  loadStudyProgress,
  saveStudyProgress,
  studyProgressKey,
} from './studyProgress'

afterEach(() => window.localStorage.clear())

describe('progresso da jornada guiada', () => {
  it('começa na primeira etapa quando ainda não há progresso', () => {
    expect(loadStudyProgress(7, 31)).toEqual({
      currentStep: 'preparar',
      completedSteps: [],
    })
  })

  it('salva o progresso separadamente por usuário e aula', () => {
    saveStudyProgress(7, 31, {
      currentStep: 'estudar',
      completedSteps: ['preparar', 'assistir'],
    })

    expect(loadStudyProgress(7, 31)).toEqual({
      currentStep: 'estudar',
      completedSteps: ['preparar', 'assistir'],
    })
    expect(loadStudyProgress(8, 31).currentStep).toBe('preparar')
    expect(loadStudyProgress(7, 32).currentStep).toBe('preparar')
  })

  it('isola aulas com o mesmo número em cursos diferentes', () => {
    saveStudyProgress(7, 'voa-level-1', 1, {
      currentStep: 'assistir',
      completedSteps: ['preparar'],
    })
    saveStudyProgress(7, 'voa-level-2', 1, {
      currentStep: 'praticar',
      completedSteps: ['preparar', 'assistir', 'estudar'],
    })

    expect(loadStudyProgress(7, 'voa-level-1', 1).currentStep).toBe('assistir')
    expect(loadStudyProgress(7, 'voa-level-2', 1).currentStep).toBe('praticar')
    expect(studyProgressKey(7, 'voa-level-1', 1)).not.toBe(
      studyProgressKey(7, 'voa-level-2', 1),
    )
  })

  it('migra o progresso local legado para o Level 1', () => {
    window.localStorage.setItem(
      'aulas-ingles:study-progress:v1:7:31',
      JSON.stringify({ currentStep: 'estudar', completedSteps: ['preparar', 'assistir'] }),
    )

    expect(loadStudyProgress(7, 'voa-level-1', 31).currentStep).toBe('estudar')
    expect(window.localStorage.getItem(studyProgressKey(7, 'voa-level-1', 31))).not.toBeNull()
  })

  it('ignora dados inválidos sem impedir que a aula abra', () => {
    window.localStorage.setItem(
      studyProgressKey(7, 31),
      JSON.stringify({
        currentStep: 'etapa-inexistente',
        completedSteps: ['preparar', 'inexistente', 'preparar'],
      }),
    )

    expect(loadStudyProgress(7, 31)).toEqual({
      currentStep: 'preparar',
      completedSteps: ['preparar'],
    })

    window.localStorage.setItem(studyProgressKey(7, 31), '{quebrado')
    expect(loadStudyProgress(7, 31).currentStep).toBe('preparar')
  })
})
