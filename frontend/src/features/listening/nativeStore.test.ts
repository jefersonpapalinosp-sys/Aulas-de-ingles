import { beforeEach, expect, it, vi } from 'vitest'
import { IDBObjectStore } from 'fake-indexeddb'
import { nativeStore } from './nativeStore'
import { syncNative } from './nativeQueue'
import { respondNative, type NativeSession, type NativeResponse } from '../../api/nativeListening'
import { setAccessToken, setSessionReadOnly, setSessionUser } from '../../api/client'
import { ApiError } from '../../api/errors'

vi.mock('../../api/nativeListening', () => ({ respondNative: vi.fn() }))
const session: NativeSession = { id: 1, revision: 0, completed: false, score: 0, total: 3,
  support_revealed: false, transcript: null, feedback: [], created_at: '2026-11-05T12:00:00Z',
  activity: { slug: 'hotel', version: 1, title: 'Hotel', level: 'A2', topic: 'Travel', preview: true,
    instructions: 'Listen', questions: [], map_rows: [], map_description: null,
    audio_duration_seconds: 70, attribution: 'Original', rights_note: 'Draft' },
}
const body = (question = 'one'): NativeResponse => ({ question_id: question, selected_ids: ['a'],
  kind: 'answer', operation_key: crypto.randomUUID(), expected_revision: 0 })
beforeEach(() => {
  vi.restoreAllMocks(); vi.mocked(respondNative).mockReset()
  setSessionUser(1); setAccessToken('synthetic'); setSessionReadOnly(false)
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
})

it('grava antes de anunciar sucesso e preserva fila após recarga e troca de conta', async () => {
  const input = body()
  await nativeStore.cache(1, 0, session)
  await nativeStore.enqueue(1, 0, session, input)
  await nativeStore.enqueue(2, 0, session, input)
  expect((await nativeStore.read(1)).commands).toHaveLength(1)
  expect((await nativeStore.read(2)).commands).toHaveLength(1)
  expect((await nativeStore.read(3)).commands).toHaveLength(0)
  expect((await nativeStore.read(1)).commands[0]?.body.operation_key).toBe(input.operation_key)
})

it('duas abas reservam revisões consecutivas e preservam variantes de rascunho', async () => {
  const original = await nativeStore.draft(1, 0, session, 'one', ['a'])
  await Promise.all([
    nativeStore.draft(1, 0, session, 'one', ['b'], original.id),
    nativeStore.draft(1, 0, session, 'one', ['c'], original.id),
  ])
  expect((await nativeStore.read(1)).drafts.map(row => row.selected[0]).sort()).toEqual(['b', 'c'])
  await Promise.all([nativeStore.enqueue(1, 0, session, body()), nativeStore.enqueue(1, 0, session, body('two'))])
  expect((await nativeStore.read(1)).commands.map(row => row.body.expected_revision)).toEqual([0, 1])
})

it('resposta confirmada não apaga rascunho concorrente nem regride snapshot', async () => {
  const draft = await nativeStore.draft(1, 0, session, 'one', ['a'])
  const command = await nativeStore.enqueue(1, 0, session, body(), draft.id)
  await nativeStore.draft(1, 0, session, 'one', ['b'])
  await nativeStore.cache(1, 0, { ...session, revision: 5 })
  await nativeStore.acknowledge(1, 0, command, { ...session, revision: 1 })
  const state = await nativeStore.read(1)
  expect(state.sessions[0]?.revision).toBe(5)
  expect(state.drafts[0]?.selected).toEqual(['b'])
  expect(state.commands).toHaveLength(0)
})

it('editar em outra aba preserva o rascunho recebido por notificação', async () => {
  const first = await nativeStore.draft(1, 0, session, 'one', ['a'], undefined, 'tab-a')
  const second = await nativeStore.draft(1, 0, session, 'one', ['b'], first.id, 'tab-b')
  await nativeStore.draft(1, 0, session, 'one', ['c'], second.id, 'tab-b')
  expect((await nativeStore.read(1)).drafts.map(row => row.selected[0]).sort()).toEqual(['a', 'c'])
})

it('quota aborta a transação e preserva escolhas anteriores', async () => {
  const draft = await nativeStore.draft(1, 0, session, 'one', ['a'])
  const spy = vi.spyOn(IDBObjectStore.prototype, 'add').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError') })
  await expect(nativeStore.enqueue(1, 0, session, body(), draft.id)).rejects.toThrow('Não foi possível salvar')
  spy.mockRestore()
  expect((await nativeStore.read(1)).drafts).toHaveLength(1)
  expect((await nativeStore.read(1)).commands).toHaveLength(0)
})

it('limpeza impede callbacks antigos de ressuscitar dados e preserva outra conta', async () => {
  const command = await nativeStore.enqueue(1, 0, session, body())
  await nativeStore.enqueue(2, 0, session, body())
  await nativeStore.clear(1)
  await expect(nativeStore.acknowledge(1, 0, command, session)).rejects.toThrow()
  await expect(nativeStore.draft(1, 0, session, 'one', ['b'])).rejects.toThrow()
  expect((await nativeStore.read(1)).commands).toHaveLength(0)
  expect((await nativeStore.read(2)).commands).toHaveLength(1)
  await nativeStore.draft(1, 1, session, 'one', ['c'])
  expect((await nativeStore.read(1)).drafts).toHaveLength(1)
})

it('resposta de outra versão não confirma a fila', async () => {
  const command = await nativeStore.enqueue(1, 0, session, body())
  await expect(nativeStore.acknowledge(1, 0, command, { ...session, activity: { ...session.activity, version: 2 } })).rejects.toThrow()
  expect((await nativeStore.read(1)).commands).toHaveLength(1)
})

it('falha transitória preserva chave e reconexão confirma uma única resposta', async () => {
  const command = await nativeStore.enqueue(1, 0, session, body())
  vi.mocked(respondNative).mockRejectedValueOnce(new Error('network')).mockResolvedValue({ ...session, revision: 1 })
  await expect(syncNative(1)).rejects.toThrow('network')
  expect((await nativeStore.read(1)).commands).toHaveLength(1)
  await Promise.all([syncNative(1), syncNative(1)])
  expect(vi.mocked(respondNative).mock.calls.map(call => call[1])).toEqual([command.body, command.body])
  expect((await nativeStore.read(1)).commands).toHaveLength(0)
})

it('conflito bloqueia só a sessão afetada até escolha explícita', async () => {
  const first = await nativeStore.enqueue(1, 0, session, body())
  await nativeStore.enqueue(1, 0, session, body('two'))
  const other = { ...session, id: 2 }
  await nativeStore.enqueue(1, 0, other, body())
  vi.mocked(respondNative).mockImplementation(id => {
    if (id === 1) return Promise.reject(new ApiError('resposta', new Response('{}', { status: 409 })))
    return Promise.resolve({ ...other, revision: 1 })
  })
  await syncNative(1)
  const state = await nativeStore.read(1)
  expect(state.commands).toHaveLength(2)
  expect(state.commands[0]?.blocked).toBe(true)
  expect(respondNative).toHaveBeenCalledTimes(2)
  await nativeStore.rebase(1, 0, first.id, { ...session, revision: 8 })
  const replacement = (await nativeStore.read(1)).commands.find(row => row.body.expected_revision === 8)!
  expect(replacement.body.operation_key).not.toBe(first.body.operation_key)
  expect(replacement.body.selected_ids).toEqual(first.body.selected_ids)
})

it('perfil não confirmado e outra conta nunca enviam respostas', async () => {
  await nativeStore.enqueue(1, 0, session, body())
  setSessionReadOnly(true); await syncNative(1)
  setSessionReadOnly(false); setSessionUser(2); await syncNative(1)
  expect(respondNative).not.toHaveBeenCalled()
})

it('troca de conta durante a rede preserva a pendência original', async () => {
  await nativeStore.enqueue(1, 0, session, body())
  let complete!: (value: NativeSession) => void
  vi.mocked(respondNative).mockImplementation(() => new Promise(resolve => { complete = resolve }))
  const sending = syncNative(1)
  await vi.waitFor(() => expect(respondNative).toHaveBeenCalledTimes(1))
  setSessionUser(2); setAccessToken('other')
  complete({ ...session, revision: 1 })
  await sending
  expect((await nativeStore.read(1)).commands).toHaveLength(1)
  expect((await nativeStore.read(2)).sessions).toHaveLength(0)
})
