// Guardas independentes do Playwright; também executadas ANTES de subir a stack.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const PROJECT = 'aulas-ingles-e2e'
export const BASE_URL = 'http://127.0.0.1:5198'
export const DATABASE_URL = 'postgresql+asyncpg://aulas_test:aulas_test_only@db:5432/aulas_ingles_test'
export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const compose = ['compose', '--env-file', 'infra/e2e.env', '-p', PROJECT, '-f', 'infra/compose.e2e.yml']
const volumeNames = ['pgdata', 'speaking_data'].map((name) => `${PROJECT}_${name}`)

function docker(args) {
  try {
    return execFileSync('docker', args, {
      cwd: ROOT, encoding: 'utf8', timeout: 30_000, stdio: ['ignore', 'pipe', 'pipe'],
    }).trim()
  } catch {
    // Não anexar stdout/stderr/inspect: podem conter credenciais do ambiente errado.
    throw new Error('E2E bloqueado: não foi possível verificar o Docker local. Use make e2e-up.')
  }
}

export function assertTarget(value = BASE_URL) {
  assert.ok(value === BASE_URL, 'E2E bloqueado: somente http://127.0.0.1:5198 é permitido; nunca dev/prod.')
  return value
}

export function assertLocalEndpoint(endpoint) {
  assert.ok(typeof endpoint === 'string' && endpoint.startsWith('unix:///'),
    'E2E exige Docker local via socket Unix (macOS/Linux); endpoints TCP/SSH são recusados.')
}

export function assertInitSource(source, platform = process.platform) {
  const expected = resolve(ROOT, 'infra/test-db-init.sql')
  assert.ok(source === expected || (platform === 'darwin' && source === '/host_mnt' + expected),
    'Init SQL inesperado')
}

export function assertVolume(volume) {
  assert.ok(volumeNames.includes(volume.Name), 'Volume E2E desconhecido')
  assert.equal(volume.Driver, 'local', 'Volume deve ser local')
  assert.equal(volume.Scope, 'local', 'Volume deve ter escopo local')
  assert.equal(Object.keys(volume.Options ?? {}).length, 0, 'Volume não pode redirecionar para outro storage')
  assert.equal(volume.Labels?.['com.docker.compose.project'], PROJECT, 'Volume de outro projeto')
  assert.equal(volume.Labels?.['com.docker.compose.volume'], volume.Name.slice(PROJECT.length + 1), 'Volume inesperado')
  assert.equal(volume.Labels?.['org.aulas.environment'], 'disposable-e2e', 'Volume sem marcador descartável')
}

export function assertGatewayNetwork(network) {
  assert.equal(network.Name, `${PROJECT}_gateway`, 'Rede do gateway inesperada')
  assert.equal(network.Driver, 'bridge', 'Rede do gateway deve ser local')
  assert.equal(network.Internal, true, 'Gateway exige rede interna')
  assert.equal(network.Labels?.['com.docker.compose.project'], PROJECT, 'Rede de outro projeto')
}

export function assertContainer(container, service) {
  assert.equal(container.Config.Labels?.['com.docker.compose.project'], PROJECT, 'Container de outro projeto')
  assert.equal(container.Config.Labels?.['com.docker.compose.service'], service, 'Serviço inesperado')
  assert.equal(container.State.Running, true, 'Serviço E2E parado')
  const networks = service === 'gateway' ? ['gateway']
    : ['api', 'worker'].includes(service) ? ['default', 'gateway'] : ['default']
  assert.deepEqual(Object.keys(container.NetworkSettings.Networks).sort(), networks.map(name => `${PROJECT}_${name}`).sort(), 'Rede não isolada')
  assert.equal(container.HostConfig.Privileged, false, 'Container privilegiado não permitido')
  const mounts = container.Mounts ?? []
  const env = Object.fromEntries(container.Config.Env.map((entry) => {
    const split = entry.indexOf('=')
    return [entry.slice(0, split), entry.slice(split + 1)]
  }))
  if (service === 'web') {
    assert.equal(mounts.length, 0, 'Web não pode montar dados do host')
    assert.deepEqual(container.HostConfig.PortBindings, {
      '80/tcp': [{ HostIp: '127.0.0.1', HostPort: '5198' }],
    }, 'Porta web inesperada')
  } else if (service === 'gateway') {
    assert.equal(mounts.length, 0, 'Gateway não pode montar dados do host')
    assert.equal(Object.keys(container.HostConfig.PortBindings ?? {}).length, 0, 'Gateway não pode publicar portas')
    assert.equal(container.Config.Image, 'aulas-ingles-e2e-gateway:local', 'Imagem inesperada')
    assert.equal(container.Config.User, '65534:65534', 'Gateway não pode executar como root')
    assert.equal(container.HostConfig.ReadonlyRootfs, true, 'Gateway deve ser somente leitura')
    assert.equal(env.E2E_GATEWAY_ONLY, 'disposable-e2e', 'Gateway sem marcador de teste')
  } else {
    assert.equal(Object.keys(container.HostConfig.PortBindings ?? {}).length, 0, 'API/banco não devem publicar portas')
    const data = mounts.find((mount) => mount.Type === 'volume')
    assert.equal(data?.Name, `${PROJECT}_${service === 'db' ? 'pgdata' : 'speaking_data'}`, 'Volume de dados incorreto')
    assert.equal(data?.Destination, service === 'db' ? '/var/lib/postgresql/data' : '/app/data/speaking', 'Destino incorreto')
    if (service === 'db') {
      assert.equal(mounts.length, 2, 'Banco com mounts inesperados')
      const init = mounts.find((mount) => mount.Type === 'bind')
      assertInitSource(init?.Source)
      assert.equal(init?.Destination, '/docker-entrypoint-initdb.d/01-test.sql', 'Init SQL fora do destino')
      assert.equal(init?.RW, false, 'Init SQL deve ser somente leitura')
      assert.equal(env.POSTGRES_USER, 'aulas_test_admin', 'Administrador inesperado')
      assert.equal(env.POSTGRES_DB, 'postgres', 'Base inicial inesperada')
    } else {
      assert.ok(['api', 'worker'].includes(service), 'Serviço não permitido')
      assert.equal(mounts.length, 1, 'API com mounts inesperados')
      assert.equal(env.APP_ENV, 'test', 'API precisa ativar as guardas de teste')
      // Não usar assert.equal aqui: o erro não pode mostrar uma URL com senha.
      assert.ok(env.DATABASE_URL === DATABASE_URL, 'API com conexão diferente da base descartável')
      assert.ok(!env.TEST_DATABASE_URL || env.TEST_DATABASE_URL === DATABASE_URL, 'Override de conexão inesperado')
      assert.equal(env.SPEAKING_STORAGE_DIR, '/app/data/speaking', 'Storage inesperado')
      assert.equal(env.ASSISTED_FEATURES_ENABLED, 'true', 'E2E exige assistência sintética')
      assert.equal(env.DIALOGUE_PRACTICE_ENABLED, 'true', 'E2E exige interface de conversa')
      assert.equal(env.ASSIST_PROVIDER_KIND, 'gateway', 'E2E só aceita gateway sintético')
      assert.equal(env.ASSIST_PROVIDER_NAME, 'synthetic-e2e', 'Provedor inesperado')
      // Não mostrar valores recebidos: uma configuração incorreta pode conter segredos.
      assert.ok(env.ASSIST_TRANSCRIPTION_URL === 'http://gateway:8080/stt', 'URL STT externa recusada')
      assert.ok(env.ASSIST_DIALOGUE_URL === 'http://gateway:8080/dialogue', 'URL de diálogo externa recusada')
      assert.ok(!env.ASSIST_WRITING_URL && !env.ASSIST_PROVIDER_TOKEN, 'Credenciais/URL externa recusadas')
      assert.equal(env.ASSIST_WRITING_ENABLED, 'false', 'Assistência externa deve estar desativada')
      assert.equal(env.ASSIST_TRANSCRIPTION_ENABLED, 'false', 'Transcrição externa deve estar desativada')
    }
  }
}

export function checkResources(requireExisting = false) {
  // Não provisionar/parar recursos num contexto remoto escolhido no terminal.
  if (process.env.DOCKER_HOST) assertLocalEndpoint(process.env.DOCKER_HOST)
  assertLocalEndpoint(docker(['context', 'inspect', '--format', '{{.Endpoints.docker.Host}}']))
  // Evita reutilizar volumes homônimos criados com bind/NFS ou por outro projeto.
  const existing = new Set(docker(['volume', 'ls', '--format', '{{.Name}}']).split('\n'))
  for (const name of volumeNames) {
    if (existing.has(name)) assertVolume(JSON.parse(docker(['volume', 'inspect', name]))[0])
    else assert.ok(!requireExisting, 'Volume E2E ausente; execute make e2e-up')
  }
  const networks = docker(['network', 'ls', '--format', '{{.Name}}']).split('\n')
  if (networks.includes(`${PROJECT}_gateway`)) {
    assertGatewayNetwork(JSON.parse(docker(['network', 'inspect', `${PROJECT}_gateway`]))[0])
  } else assert.ok(!requireExisting, 'Rede interna do gateway ausente')
}

export function readSentinel() {
  const value = docker([...compose, 'exec', '-T', 'db', 'psql', '-XAt', '-v', 'ON_ERROR_STOP=1',
    '-U', 'aulas_test_admin', '-d', 'aulas_test_sentinel', '-c',
    'SELECT id, value FROM isolation_sentinel ORDER BY id'])
  assert.equal(value, '1|preserve-this-synthetic-record', 'Sentinela sintética alterada')
  return value
}

export async function checkStack(baseURL = BASE_URL) {
  assertTarget(baseURL)
  checkResources(true)
  for (const service of ['db', 'api', 'web', 'worker', 'gateway']) {
    const id = docker([...compose, 'ps', '-q', service])
    assert.match(id, /^[a-f0-9]+$/, 'Serviço E2E ausente ou ambíguo')
    assertContainer(JSON.parse(docker(['inspect', id]))[0], service)
  }
  // Confirma current_database/current_user, marcador e privilégios reais, não só env.
  docker([...compose, 'exec', '-T', 'api', 'python', '-m', 'app.testing', 'check'])
  const response = await fetch(`${baseURL}/api/health`, {
    redirect: 'error', signal: AbortSignal.timeout(10_000),
  })
  assert.equal(response.status, 200, 'Readiness E2E falhou')
  const health = await response.json()
  // Identidade test já foi comprovada nos containers e no banco acima.
  // A resposta pública não divulga ambiente ou revisões (BE-49).
  assertPublicReadiness(health)
}

export function assertPublicReadiness(health) {
  assert.ok(health?.db === 'up' && health.status === 'ok' && health.schema === 'compatible', 'Readiness pública incompatível')
  for (const field of ['env', 'version', 'schema_current', 'schema_required']) {
    assert.ok(!(field in health), 'Readiness pública expõe detalhes internos')
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    assertTarget(process.env.E2E_BASE_URL)
    if (process.argv[2] === 'resources') checkResources()
    else if (process.argv[2] === 'stack') await checkStack()
    else throw new Error('uso: node e2e/safety.mjs resources | stack')
    console.log('✓ isolamento E2E verificado')
  } catch {
    console.error('E2E bloqueado: alvo/recursos não verificados. Use exclusivamente make e2e-up e a porta 5198.')
    process.exitCode = 1
  }
}
