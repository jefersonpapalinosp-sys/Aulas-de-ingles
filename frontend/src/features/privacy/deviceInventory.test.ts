import { beforeEach, describe, expect, it, vi } from 'vitest'
import { queueAttempt } from '../offline/attemptQueue'
import { clearVoiceDraft, retainVoiceDraft, takeVoiceDraft } from '../speaking/voiceDraft'
import { clearDeviceData, inspectDevice } from './deviceInventory'

describe('inventário local privado', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('isola a conta, separa cópias e filas e não consome a gravação', async () => {
    localStorage.setItem('aulas-ingles:writing-draft:v1:1:3', 'meu texto')
    localStorage.setItem('aulas-ingles:writing-draft:v1:1:3:revision', '0')
    localStorage.setItem('aulas-ingles:writing-draft:v1:10:3', 'outra conta')
    localStorage.setItem('aulas-ingles:media-pending:v2:1:12:command', '{}')
    localStorage.setItem('aulas-ingles:activity-event:v1:1:event', '{}')
    localStorage.setItem('aulas-ingles:study-progress:v2:1:voa-level-1:31', '{}')
    await queueAttempt({ userId: 1, exerciseId: 1, answer: 'private', idempotencyKey: 'a', createdAt: new Date().toISOString() })
    await queueAttempt({ userId: 10, exerciseId: 2, answer: 'other', idempotencyKey: 'b', createdAt: new Date().toISOString() })
    retainVoiceDraft({ key: '1:voa-level-1:31:2', blob: new Blob(['audio']), duration: 1, attemptId: null })
    const before = { ...localStorage }
    expect(await inspectDevice(1)).toEqual({ drafts: 1, mediaCommands: 1, activityEvents: 1,
      localCopies: 1, pendingAnswers: 1, blockedAnswers: 0, voiceDraft: true })
    expect(await inspectDevice(10)).toMatchObject({ drafts: 1, voiceDraft: false })
    expect({ ...localStorage }).toEqual(before)
    expect(takeVoiceDraft('1:voa-level-1:31:2')).not.toBeNull()
  })

  it('reporta incerteza, não zero, quando o armazenamento falha', async () => {
    vi.spyOn(Storage.prototype, 'key').mockImplementation(() => { throw new Error('blocked') })
    localStorage.setItem('test', 'x')
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    expect(await inspectDevice(1)).toMatchObject({ drafts: null, mediaCommands: null,
      activityEvents: null, localCopies: null, pendingAnswers: null })
    clearVoiceDraft('1:voa-level-1:31:2')
  })

  it('limpa somente dados privados da conta escolhida', async () => {
    localStorage.setItem('aulas-ingles:writing-draft:v1:31:3', 'apagar')
    localStorage.setItem('aulas-ingles:writing-draft:v1:32:3', 'preservar')
    localStorage.setItem('public-cache', 'preservar')
    await queueAttempt({ userId: 31, exerciseId: 1, answer: 'private',
      idempotencyKey: 'clear-31', createdAt: new Date().toISOString() })
    await queueAttempt({ userId: 32, exerciseId: 1, answer: 'other',
      idempotencyKey: 'keep-32', createdAt: new Date().toISOString() })
    retainVoiceDraft({ key: '31:voa-level-1:31:2', blob: new Blob(['audio']),
      duration: 1, attemptId: null })

    expect(await clearDeviceData(31)).toBe(2)
    expect(await inspectDevice(31)).toMatchObject({ drafts: 0, pendingAnswers: 0,
      blockedAnswers: 0, voiceDraft: false })
    expect(await inspectDevice(32)).toMatchObject({ drafts: 1, pendingAnswers: 1 })
    expect(localStorage.getItem('public-cache')).toBe('preservar')
  })
})
