import { expect, it, vi } from 'vitest'
import { ActivityClock } from './activityClock'

it('emite blocos de 15 segundos somente enquanto ativo', () => {
  const emit = vi.fn(), clock = new ActivityClock(0, emit)
  clock.tick(0, true)
  for (let second = 1; second <= 30; second++) clock.tick(second * 1000, true)
  expect(emit.mock.calls).toEqual([[15000, 15000], [30000, 15000]])
})
it('ocultação, abandono, suspensão e retorno não acumulam o intervalo ausente', () => {
  const emit = vi.fn(), clock = new ActivityClock(0, emit)
  clock.tick(0, true); clock.tick(1000, true); clock.tick(2000, false)
  clock.tick(1800000, false); clock.tick(1801000, true); clock.tick(1802000, true)
  clock.tick(3600000, true); clock.tick(3601000, true); clock.flush()
  expect(emit.mock.calls).toEqual([[1000, 1000], [1802000, 1000], [3601000, 1000]])
})
it('flush de saída é idempotente e não inventa tempo antes do primeiro sinal', () => {
  const emit = vi.fn(), clock = new ActivityClock(0, emit)
  clock.tick(1000, true); clock.flush(); expect(emit).not.toHaveBeenCalled()
  clock.tick(2000, true); clock.flush(); clock.flush()
  expect(emit.mock.calls).toEqual([[2000, 1000]])
})
