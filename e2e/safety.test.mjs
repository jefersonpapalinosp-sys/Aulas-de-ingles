import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import test from 'node:test'
import { assertContainer, assertGatewayNetwork, assertInitSource, assertLocalEndpoint, assertPublicReadiness, assertTarget, assertVolume, BASE_URL, DATABASE_URL, PROJECT, ROOT } from './safety.mjs'

test('readiness pública exige schema compatível e não divulga diagnóstico interno', () => {
  const healthy = { status: 'ok', db: 'up', schema: 'compatible', code: null }
  assertPublicReadiness(healthy)
  for (const bad of [null, {}, { ...healthy, schema: 'incompatible' }, { ...healthy, db: 'down' }]) {
    assert.throws(() => assertPublicReadiness(bad))
  }
  for (const field of ['env', 'version', 'schema_current', 'schema_required']) {
    assert.throws(() => assertPublicReadiness({ ...healthy, [field]: 'internal' }))
  }
})

test('alias Docker Desktop é exato e exclusivo do macOS', () => {
  const path = resolve(ROOT, 'infra/test-db-init.sql')
  assertInitSource(path, 'linux')
  assertInitSource('/host_mnt' + path, 'darwin')
  assert.throws(() => assertInitSource('/host_mnt' + path, 'linux'))
  assert.throws(() => assertInitSource('/host_mnt' + path + '.wrong', 'darwin'))
})

test('assistência só pode apontar para o gateway sintético', () => {
  const value = container('api')
  value.Config.Env = value.Config.Env.map((entry) => entry.replace('ASSIST_DIALOGUE_URL=http://gateway:8080/dialogue', 'ASSIST_DIALOGUE_URL=https://external.invalid/dialogue'))
  assert.throws(() => assertContainer(value, 'api'))
})

function volume() {
  return {
    Name: `${PROJECT}_pgdata`, Driver: 'local', Scope: 'local', Options: null,
    Labels: {
      'com.docker.compose.project': PROJECT, 'com.docker.compose.volume': 'pgdata',
      'org.aulas.environment': 'disposable-e2e',
    },
  }
}

function container(service) {
  return {
    Config: {
      Labels: { 'com.docker.compose.project': PROJECT, 'com.docker.compose.service': service },
      Image: 'aulas-ingles-e2e-gateway:local', User: '65534:65534',
      Env: [
        'APP_ENV=test', `DATABASE_URL=${DATABASE_URL}`, 'SPEAKING_STORAGE_DIR=/app/data/speaking',
        'POSTGRES_USER=aulas_test_admin', 'POSTGRES_DB=postgres',
        'ASSIST_WRITING_ENABLED=false', 'ASSIST_TRANSCRIPTION_ENABLED=false',
        'ASSISTED_FEATURES_ENABLED=true', 'DIALOGUE_PRACTICE_ENABLED=true',
        'ASSIST_PROVIDER_KIND=gateway', 'ASSIST_PROVIDER_NAME=synthetic-e2e',
        'ASSIST_DIALOGUE_URL=http://gateway:8080/dialogue', 'ASSIST_TRANSCRIPTION_URL=http://gateway:8080/stt',
        'E2E_GATEWAY_ONLY=disposable-e2e',
      ],
    },
    State: { Running: true },
    NetworkSettings: { Networks: Object.fromEntries(
      (service === 'gateway' ? ['gateway'] : ['api', 'worker'].includes(service) ? ['default', 'gateway'] : ['default'])
        .map(name => [`${PROJECT}_${name}`, {}])), },
    HostConfig: {
      Privileged: false, ReadonlyRootfs: true,
      PortBindings: service === 'web' ? { '80/tcp': [{ HostIp: '127.0.0.1', HostPort: '5198' }] } : {},
    },
    Mounts: ['web', 'gateway'].includes(service) ? [] : ['api', 'worker'].includes(service) ? [
      { Type: 'volume', Name: `${PROJECT}_speaking_data`, Destination: '/app/data/speaking' },
    ] : [
      { Type: 'volume', Name: `${PROJECT}_pgdata`, Destination: '/var/lib/postgresql/data' },
      { Type: 'bind', Source: resolve(ROOT, 'infra/test-db-init.sql'), Destination: '/docker-entrypoint-initdb.d/01-test.sql', RW: false },
    ],
  }
}

test('somente a origem descartável exata é aceita (inclusive no padrão)', () => {
  assert.equal(assertTarget(), BASE_URL)
  assert.equal(assertTarget(BASE_URL), BASE_URL)
})
test('aceita sockets Unix locais de macOS/Linux', () => {
  assertLocalEndpoint('unix:///var/run/docker.sock')
  assertLocalEndpoint('unix:///Users/test/.docker/run/docker.sock')
})
for (const endpoint of ['tcp://production:2375', 'tcp://127.0.0.1:2375', 'ssh://remote', 'https://remote', undefined]) {
  test(`recusa endpoint Docker não local: ${endpoint}`, () => assert.throws(() => assertLocalEndpoint(endpoint)))
}
test('CLI recusa DOCKER_HOST remoto antes de consultar recursos', () => {
  const result = spawnSync(process.execPath, ['e2e/safety.mjs', 'resources'], {
    cwd: ROOT, encoding: 'utf8', env: { ...process.env, DOCKER_HOST: 'tcp://production:2375' },
  })
  assert.equal(result.status, 1)
  assert.match(result.stderr, /E2E bloqueado/)
})
for (const url of ['http://localhost:5180', 'http://localhost:5181', 'https://example.org',
  'http://localhost:5198', `${BASE_URL}/`, `${BASE_URL}/api`, '', 'http://secret:password@127.0.0.1:5198']) {
  test(`bloqueia alvo alternativo ${url.replace('secret:password@', '')}`, () => {
    assert.throws(() => assertTarget(url))
  })
}
test('CLI recusa produção antes de acessar Docker e sem revelar a URL', () => {
  const result = spawnSync(process.execPath, ['e2e/safety.mjs', 'stack'], {
    cwd: ROOT, encoding: 'utf8', env: { ...process.env, E2E_BASE_URL: 'http://secret:password@localhost:5181' },
  })
  assert.equal(result.status, 1)
  assert.match(result.stderr, /E2E bloqueado/)
  assert.doesNotMatch(result.stderr, /secret|password/)
})
test('aceita volume dedicado com labels e sem redirecionamento', () => assertVolume(volume()))
for (const [label, change] of [
  ['produção', (v) => { v.Name = 'aulas-ingles-pgdata-prod' }],
  ['outro projeto', (v) => { v.Labels['com.docker.compose.project'] = 'aulas-ingles-prod' }],
  ['sem marcador', (v) => { delete v.Labels['org.aulas.environment'] }],
  ['sem labels', (v) => { v.Labels = null }],
  ['bind disfarçado', (v) => { v.Options = { type: 'none', o: 'bind', device: '/real-study' } }],
  ['driver remoto', (v) => { v.Driver = 'nfs' }],
  ['escopo global', (v) => { v.Scope = 'global' }],
]) test(`rejeita volume: ${label}`, () => {
  const value = volume()
  change(value)
  assert.throws(() => assertVolume(value))
})
for (const service of ['db', 'api', 'web', 'worker', 'gateway']) {
  test(`aceita configuração isolada de ${service}`, () => assertContainer(container(service), service))
}
for (const [label, service, change] of [
  ['projeto errado', 'api', (c) => { c.Config.Labels['com.docker.compose.project'] = 'aulas-ingles-prod' }],
  ['serviço errado', 'api', (c) => { c.Config.Labels['com.docker.compose.service'] = 'worker' }],
  ['parado', 'api', (c) => { c.State.Running = false }],
  ['rede extra', 'api', (c) => { c.NetworkSettings.Networks.production = {} }],
  ['privilegiado', 'api', (c) => { c.HostConfig.Privileged = true }],
  ['voz real', 'api', (c) => { c.Mounts[0].Name = 'aulas-ingles-speaking-data-prod' }],
  ['voz host', 'api', (c) => { c.Mounts[0].Type = 'bind' }],
  ['mount extra', 'api', (c) => { c.Mounts.push({ Type: 'bind', Source: '/real-study' }) }],
  ['porta DB', 'db', (c) => { c.HostConfig.PortBindings['5432/tcp'] = [] }],
  ['init alterado', 'db', (c) => { c.Mounts[1].Source = '/wrong/init.sql' }],
  ['init gravável', 'db', (c) => { c.Mounts[1].RW = true }],
  ['porta web real', 'web', (c) => { c.HostConfig.PortBindings['80/tcp'][0].HostPort = '5181' }],
  ['web público', 'web', (c) => { c.HostConfig.PortBindings['80/tcp'][0].HostIp = '0.0.0.0' }],
  ['web com mount', 'web', (c) => { c.Mounts.push({ Type: 'bind' }) }],
  ...['APP_ENV=prod', 'DATABASE_URL=secret', 'TEST_DATABASE_URL=secret', 'SPEAKING_STORAGE_DIR=/real-study',
    'ASSIST_WRITING_ENABLED=true', 'ASSIST_TRANSCRIPTION_ENABLED=true',
    'ASSIST_DIALOGUE_URL=https://external.invalid', 'ASSIST_TRANSCRIPTION_URL=http://host.docker.internal:9999',
    'ASSIST_PROVIDER_KIND=ollama', 'ASSIST_PROVIDER_TOKEN=secret', 'ASSIST_WRITING_URL=https://external.invalid',
    'DIALOGUE_PRACTICE_ENABLED=false'].map((env) => [
    env.split('=')[0], 'api', (c) => { c.Config.Env.push(env) },
  ]),
]) test(`rejeita container: ${label}`, () => {
  const value = container(service)
  change(value)
  assert.throws(() => assertContainer(value, service))
})

for (const [label, change] of [
  ['porta pública', c => { c.HostConfig.PortBindings = { '8080/tcp': [] } }],
  ['rede padrão', c => { c.NetworkSettings.Networks[`${PROJECT}_default`] = {} }],
  ['mount', c => { c.Mounts.push({ Type: 'bind' }) }],
  ['root', c => { c.Config.User = 'root' }],
  ['gravável', c => { c.HostConfig.ReadonlyRootfs = false }],
]) test(`recusa gateway: ${label}`, () => {
  const value = container('gateway'); change(value)
  assert.throws(() => assertContainer(value, 'gateway'))
})
test('rede do gateway precisa ser interna e pertencer ao laboratório', () => {
  const network = { Name: `${PROJECT}_gateway`, Driver: 'bridge', Internal: true,
    Labels: { 'com.docker.compose.project': PROJECT } }
  assertGatewayNetwork(network)
  assert.throws(() => assertGatewayNetwork({ ...network, Internal: false }))
  assert.throws(() => assertGatewayNetwork({ ...network, Labels: {} }))
})
