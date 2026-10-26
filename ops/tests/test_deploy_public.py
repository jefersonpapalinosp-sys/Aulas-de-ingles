"""Deploy público sem VM: ssh, git e curl simulados; recusas, sequência e gates conferidos."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops" / "deploy_public.sh"
SHA = "0ebb9be"
FULL_SHA = SHA + "0" * 33
HOST = "root@72.61.39.94"
URL = "https://papalino-aulas-ingles.aeuv6j.easypanel.host"
CODE = "/etc/easypanel/projects/papalino/aulas-ingles/code"
STAGE = f"/tmp/aulas-deploy-{FULL_SHA}"
COMPOSE_UP = (
    "docker compose -p papalino_aulas-ingles --env-file .env -f compose.yml "
    "-f docker-compose.override.yml up -d --build --remove-orphans --wait --wait-timeout 420"
)
RSYNC = (
    "rsync -a --delete --exclude=/docker-compose.override.yml --exclude=/infra/easypanel/.env "
    f"--exclude=/infra/easypanel/docker-compose.override.yml {STAGE}/ {CODE}/"
)
SMOKE_PATHS = ["/", "/sw.js", "/api/live", "/api/health", "/api/courses"]
HEALTH = {
    "status": "ok",
    "db": "up",
    "schema": "compatible",
    "schema_current": ["d2b7e4c9a150"],
    "schema_required": ["d2b7e4c9a150"],
    "env": "prod",
}
# Cada mock registra a chamada no arquivo de rastro e responde conforme o
# conteúdo do comando remoto, como a VM responderia.
MOCKS = r"""
trace() { printf 'CALL %s\n' "$*" >> "$DEPLOY_TEST_TRACE"; }
git() {
  trace git "$@"
  case "$1" in
    rev-parse)
      [ "$DEPLOY_TEST_MODE" != missing ] || return 1
      printf '%s\n' "$DEPLOY_TEST_FULL_SHA" ;;
    merge-base) [ "$DEPLOY_TEST_MODE" != not_ancestor ] ;;
    archive) printf 'TAR-SINTETICO' ;;
    *) return 1 ;;
  esac
}
ssh() {
  trace ssh "$@"
  local remote
  for remote in "$@"; do :; done
  case "$remote" in
    *"tar -x"*) trace "stdin $(cat)" ;;
    *"docker inspect"*)
      printf 'migrate %s\npermissions %s\nseed absent\n' \
        "${DEPLOY_TEST_MIGRATE_EXIT:-0}" "${DEPLOY_TEST_PERMISSIONS_EXIT:-0}" ;;
    *" up -d "*) return "${DEPLOY_TEST_UP_EXIT:-0}" ;;
    *" ps -a"*) printf 'SERVICE STATUS\nmigrate Exited (0)\n' ;;
  esac
}
curl() {
  trace curl "$@"
  local out="" url=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -o) out="$2"; shift ;;
      http*) url="$1" ;;
    esac
    shift
  done
  if [ -n "$out" ]; then
    case "$url" in
      *"/api/health") printf '%s' "$DEPLOY_TEST_HEALTH" > "$out" ;;
      *) printf 'corpo' > "$out" ;;
    esac
  fi
  case "$url" in
    *"${DEPLOY_TEST_HTTP_500_PATH:-/nunca}") printf '500' ;;
    *) printf '200' ;;
  esac
}
rsync() { trace rsync "$@"; return 1; }
scp() { trace scp "$@"; return 1; }
sleep() { trace sleep "$@"; }
script="$1"
shift
source "$script" "$@"
"""


class DeployPublicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.trace = Path(self.tmp.name) / "trace"
        self.trace.touch()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, mode="ok", health=HEALTH, **extra):
        # O ambiente do terminal não pode vazar host/URL para o teste; só `extra`
        # (o cenário) pode definir essas variáveis.
        base = {
            k: v
            for k, v in os.environ.items()
            if k not in ("AULAS_PUBLIC_SSH_HOST", "AULAS_PUBLIC_URL")
        }
        env = {
            **base,
            "DEPLOY_TEST_TRACE": str(self.trace),
            "DEPLOY_TEST_MODE": mode,
            "DEPLOY_TEST_FULL_SHA": FULL_SHA,
            "DEPLOY_TEST_HEALTH": json.dumps(health),
            **extra,
        }
        return subprocess.run(
            ["bash", "-e", "-s", str(SCRIPT), *args],
            input=MOCKS,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=20,
        )

    def calls(self, program):
        prefix = f"CALL {program} "
        return [line for line in self.trace.read_text().splitlines() if line.startswith(prefix)]

    def test_refuses_branch_names_before_touching_git_or_the_vm(self):
        result = self.run_script("main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::SHA inválido", result.stdout)
        self.assertEqual(self.trace.read_text(), "")

    def test_refuses_unknown_commit_without_remote_calls(self):
        result = self.run_script(SHA, mode="missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("não existe neste clone", result.stdout)
        self.assertTrue(any("rev-parse" in call for call in self.calls("git")))
        self.assertEqual(self.calls("ssh"), [])

    def test_refuses_commit_outside_origin_main(self):
        result = self.run_script(SHA, mode="not_ancestor")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("não está integrado em origin/main", result.stdout)
        merge_base = [call for call in self.calls("git") if "merge-base --is-ancestor" in call]
        self.assertEqual(len(merge_base), 1)
        self.assertIn(f"{FULL_SHA} origin/main", merge_base[0])
        self.assertEqual(self.calls("ssh"), [])
        self.assertEqual(self.calls("curl"), [])

    def test_requires_a_sha_even_when_make_passes_an_empty_one(self):
        result = self.run_script("")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("informe o SHA", result.stdout)
        self.assertEqual(self.trace.read_text(), "")

    def test_dry_run_prints_every_command_without_remote_calls(self):
        result = self.run_script("--dry-run", SHA)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for expected in (
            f"git archive --format=tar {FULL_SHA} | ssh {HOST} -- rm -rf {STAGE} "
            f"&& mkdir -p {STAGE}",
            RSYNC,
            f"> {CODE}/.deployed-sha",
            f"cd {CODE}/infra/easypanel && {COMPOSE_UP}",
            "docker inspect -f '{{.State.ExitCode}}'",
            f"{URL}/api/health",
            "Dry-run concluído",
        ):
            self.assertIn(expected, result.stdout)
        self.assertEqual(
            [line[:9] for line in result.stdout.splitlines() if " ssh " in line][0], "[dry-run]"
        )
        self.assertEqual(self.calls("ssh"), [])
        self.assertEqual(self.calls("curl"), [])
        self.assertEqual(self.calls("rsync"), [])
        self.assertEqual(self.calls("scp"), [])
        # git só valida o SHA localmente; o archive não roda em dry-run.
        self.assertFalse(any(" archive " in call for call in self.calls("git")))

    def test_full_sequence_matches_the_registered_procedure(self):
        result = self.run_script(SHA)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        ssh_calls = self.calls("ssh")
        for call in ssh_calls:
            self.assertIn("-o BatchMode=yes", call)
            self.assertIn("-o StrictHostKeyChecking=yes", call)
            self.assertIn(f" {HOST} ", call)
        expected_order = [
            f"test -f {CODE}/infra/easypanel/.env",
            f"tar -x -C {STAGE}",
            RSYNC,
            f"cd {CODE}/infra/easypanel && {COMPOSE_UP}",
            " ps -a",
            "docker inspect -f '{{.State.ExitCode}}'",
        ]
        position = -1
        for fragment in expected_order:
            matches = [index for index, call in enumerate(ssh_calls) if fragment in call]
            self.assertTrue(matches, f"{fragment!r} ausente em {ssh_calls}")
            self.assertGreater(matches[0], position, f"{fragment!r} fora de ordem")
            position = matches[0]
        self.assertEqual(len(ssh_calls), len(expected_order))
        sync = [call for call in ssh_calls if RSYNC in call][0]
        self.assertIn(f"{FULL_SHA} ", sync)
        self.assertIn(f"> {CODE}/.deployed-sha && rm -rf {STAGE}", sync)
        self.assertIn("CALL stdin TAR-SINTETICO", self.trace.read_text())
        smokes = [call.split()[-1] for call in self.calls("curl")]
        self.assertEqual(smokes, [URL + path for path in SMOKE_PATHS])
        self.assertIn("migrate: saída 0", result.stdout)
        self.assertIn("permissions: saída 0", result.stdout)
        self.assertIn("seed: sem serviço próprio", result.stdout)
        self.assertIn(
            "schema_current=['d2b7e4c9a150'] schema_required=['d2b7e4c9a150']", result.stdout
        )
        self.assertIn(f"Deploy público concluído: {FULL_SHA}", result.stdout)
        # O .env remoto nunca é lido nem impresso; só referenciado por --env-file.
        self.assertFalse(any("cat " in call for call in ssh_calls))
        self.assertNotIn("EASYPANEL_", result.stdout)
        self.assertEqual(self.calls("rsync"), [])
        self.assertEqual(self.calls("scp"), [])

    def test_one_shot_exit_code_fails_the_deploy_before_smokes(self):
        result = self.run_script(SHA, DEPLOY_TEST_MIGRATE_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::migrate: saída 1", result.stdout)
        self.assertIn("permissions: saída 0", result.stdout)
        self.assertIn("gate de release reprovado", result.stdout)
        self.assertTrue(
            any("logs --no-color --tail=80 migrate permissions" in c for c in self.calls("ssh"))
        )
        self.assertEqual(self.calls("curl"), [])

    def test_compose_up_failure_still_shows_state_and_fails(self):
        result = self.run_script(SHA, DEPLOY_TEST_UP_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(" ps -a" in call for call in self.calls("ssh")))
        self.assertIn("compose up saiu com 1", result.stdout)
        self.assertEqual(self.calls("curl"), [])

    def test_smoke_500_fails_after_bounded_retries(self):
        result = self.run_script(SHA, DEPLOY_TEST_HTTP_500_PATH="/api/courses")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::smoke /api/courses não respondeu 200", result.stdout)
        courses = [call for call in self.calls("curl") if call.endswith("/api/courses")]
        self.assertEqual(len(courses), 3)
        self.assertEqual(self.calls("sleep"), ["CALL sleep 5", "CALL sleep 5"])
        self.assertNotIn("Deploy público concluído", result.stdout)

    def test_schema_mismatch_in_health_fails(self):
        result = self.run_script(SHA, health={**HEALTH, "schema_current": ["a42c7d1e9f20"]})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::schema_current difere de schema_required", result.stdout)
        self.assertNotIn("Deploy público concluído", result.stdout)

    def test_skip_smoke_runs_no_curl(self):
        result = self.run_script("--skip-smoke", SHA)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls("curl"), [])
        self.assertIn("smokes HTTPS pulados", result.stdout)

    def test_host_override_is_honoured(self):
        result = self.run_script(SHA, AULAS_PUBLIC_SSH_HOST="deploy@exemplo.invalid")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(all(" deploy@exemplo.invalid " in call for call in self.calls("ssh")))
        self.assertNotIn(HOST, self.trace.read_text())

    def test_shell_syntax_and_makefile_targets(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn('bash ops/deploy_public.sh "$(sha)"', makefile)
        self.assertIn('bash ops/deploy_public.sh --dry-run "$(sha)"', makefile)
        self.assertIn(".PHONY: deploy-public deploy-public-dry-run", makefile)
