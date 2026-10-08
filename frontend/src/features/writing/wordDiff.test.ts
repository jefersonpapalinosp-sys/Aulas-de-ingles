import { describe, expect, it } from 'vitest'
import { wordDiff } from './wordDiff'

describe('wordDiff', () => {
  it('marca palavras removidas e adicionadas sem perder as iguais', () => {
    expect(wordDiff('The bus is fast.', 'The train is faster.')).toEqual([
      { kind: 'same', text: 'The' },
      { kind: 'removed', text: 'bus' },
      { kind: 'added', text: 'train' },
      { kind: 'same', text: 'is' },
      { kind: 'removed', text: 'fast' },
      { kind: 'added', text: 'faster' },
      { kind: 'same', text: '.' },
    ])
  })

  it('lida com texto vazio nos dois lados', () => {
    expect(wordDiff('', 'Write more')).toEqual([
      { kind: 'added', text: 'Write' },
      { kind: 'added', text: 'more' },
    ])
    expect(wordDiff('Old text', '')).toEqual([
      { kind: 'removed', text: 'Old' },
      { kind: 'removed', text: 'text' },
    ])
  })
})
