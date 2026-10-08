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
