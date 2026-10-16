import { afterEach, describe, expect, it, vi } from 'vitest'
import { PositionConflict, PositionSync, type Position, type PositionCommand } from './positionSync'

const initial = (): Position => ({ media_id: 9, position_seconds: 0, updated_at: null, revision: 0, completed: false, operation_key: null, changed_at: null })
function server() {
  let remote = initial()
  let online = false
  const read = vi.fn(async () => remote)
  const save = vi.fn(async (body: PositionCommand) => {
    if (body.expected_revision !== remote.revision) throw new PositionConflict(remote)
    remote = { ...remote, ...body, completed: body.completed ?? false, revision: remote.revision + 1, updated_at: new Date().toISOString() }
    return remote
  })
  return { read, save, allowed: () => online, connect: () => { online = true }, disconnect: () => { online = false },
    remote: () => remote, change: (p: number) => { remote = { ...remote, position_seconds: p, revision: remote.revision + 1, updated_at: new Date().toISOString() } } }
}
afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

describe('PositionSync', () => {
  it('preserva fila offline ao remontar e envia posição seguida de conclusão em ordem', async () => {
    const transport = server()
    const one = new PositionSync(7, 9, transport)
    one.record(30); one.record(0, true); one.dispose()
    const two = new PositionSync(7, 9, transport)
    expect(two.snapshot()).toMatchObject({ position: 0, completed: true, pending: 2 })
    transport.connect(); await two.sync()
    expect(transport.save.mock.calls.map(([body]) => body.expected_revision)).toEqual([0, 1])
    expect(transport.remote()).toMatchObject({ position_seconds: 0, completed: true, revision: 2 })
    expect(two.snapshot().pending).toBe(0)
  })
  it('conflito não sobrescreve avanço offline; escolha local usa nova revisão', async () => {
    const transport = server(), sync = new PositionSync(7, 9, transport)
    sync.record(70); transport.change(20); transport.connect(); await sync.sync()
    expect(sync.snapshot()).toMatchObject({ position: 70, pending: 1, conflict: { position_seconds: 20 } })
    expect(transport.save).not.toHaveBeenCalled()
    await sync.resolve('local')
    expect(transport.remote()).toMatchObject({ position_seconds: 70, revision: 2 })
    expect(sync.snapshot().conflict).toBeNull()
  })
  it('escolha da conta é explícita e não toca fila de outra conta', async () => {
    const transport = server(), sync = new PositionSync(7, 9, transport)
    new PositionSync(8, 9, transport).record(80)
    sync.record(70); transport.change(20); transport.connect(); await sync.sync(); await sync.resolve('remote')
    expect(sync.snapshot()).toMatchObject({ position: 20, pending: 0, conflict: null })
    expect(new PositionSync(8, 9, transport).snapshot().pending).toBe(1)
  })
  it('resposta perdida é reconhecida pelo recibo sem repetir avanço', async () => {
    const transport = server(), realSave = transport.save.getMockImplementation()!
    transport.save.mockImplementationOnce(async (body) => { await realSave(body); throw new Error('rede') })
    const sync = new PositionSync(7, 9, transport)
    sync.record(42); transport.connect(); await sync.sync()
    expect(sync.snapshot().pending).toBe(1)
    await sync.sync()
    expect(sync.snapshot().pending).toBe(0)
    expect(transport.save).toHaveBeenCalledOnce()
  })
  it('não envia nem acusa sucesso sem conta confirmada', async () => {
    const transport = server(), sync = new PositionSync(7, 9, transport)
    sync.record(42); await sync.sync()
    expect(transport.read).not.toHaveBeenCalled()
    expect(sync.snapshot().pending).toBe(1)
  })
  it('quota mantém comando em memória e avisa; remoção falha preserva recibo', async () => {
    const transport = server(), sync = new PositionSync(7, 9, transport)
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('', 'QuotaExceededError') })
    sync.record(42)
    expect(sync.snapshot().warning).toContain('retomada local não está garantida')
    write.mockRestore()
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new DOMException('', 'SecurityError') })
    transport.connect(); await sync.sync()
    expect(transport.remote().position_seconds).toBe(42)
    expect(sync.snapshot().pending).toBe(1)
    expect(sync.snapshot().warning).not.toBe('')
  })
  it('duas abas mantêm operações próprias e reconhecem recibos já confirmados', async () => {
    const transport = server(), one = new PositionSync(7, 9, transport), two = new PositionSync(7, 9, transport)
    one.record(20); two.record(40)
    expect(localStorage.length).toBe(2)
    transport.connect(); await one.sync(); await two.sync()
    expect(transport.remote().position_seconds).toBe(40)
    expect(two.snapshot()).toMatchObject({ conflict: null, pending: 0, confirmed: true })
  })
  it('legado sem data não vence posição remota automaticamente', async () => {
    localStorage.setItem('aulas-ingles:media-position:v1:7:9', '80')
    const transport = server(); transport.change(20); transport.connect()
    const sync = new PositionSync(7, 9, transport); await sync.sync()
    expect(sync.snapshot()).toMatchObject({ position: 80, conflict: { position_seconds: 20 } })
    await sync.resolve('remote')
    expect(sync.snapshot().position).toBe(20)
  })
  it('desmontagem durante GET impede envio posterior', async () => {
    const transport = server(), sync = new PositionSync(7, 9, transport)
    sync.record(30); transport.connect()
    let finish!: (value: Position) => void
    transport.read.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const work = sync.sync(); sync.dispose(); finish(initial()); await work
    expect(transport.save).not.toHaveBeenCalled()
    expect(sync.snapshot().pending).toBe(1)
  })
  it('cache disponível não é apresentado como confirmação atual da conta', async () => {
    const transport = server(), sync = new PositionSync(7, 9, transport)
    transport.connect(); await sync.sync(); transport.disconnect()
    expect(new PositionSync(7, 9, transport).snapshot()).toMatchObject({ ready: true, confirmed: false })
  })
})
