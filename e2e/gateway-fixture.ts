import { execFileSync } from 'node:child_process'
import { assertTarget, ROOT } from './safety.mjs'

export type Scenario = 'success' | 'slow' | 'failure' | 'invalid'
type Call = { key: string; bytes: number; content_type: string }

/** Controle só por exec no container já validado pelo globalSetup, sem porta no host. */
function command(action: 'control' | 'metrics', body?: object) {
  assertTarget(process.env.E2E_BASE_URL)
  const args = ['compose', '--env-file', 'infra/e2e.env', '-p', 'aulas-ingles-e2e',
    '-f', 'infra/compose.e2e.yml', 'exec', '-T', 'gateway', 'python', 'gateway.py', action]
  if (body) args.push(JSON.stringify(body))
  return JSON.parse(execFileSync('docker', args, {
    cwd: ROOT, encoding: 'utf8', timeout: 10_000, stdio: ['ignore', 'pipe', 'pipe'],
  }))
}

export function configureGateway(dialogue: Scenario = 'success', stt: Scenario = 'success') {
  command('control', { dialogue, stt })
}
export function gatewayCalls(): { stt: Call[]; dialogue: Call[] } {
  return command('metrics')
}
