"""Contrato do cliente restrito; nenhum contato com servidor real."""

import contextlib
import io
import os
import unittest
from unittest.mock import patch

from ops import deploy_client, deploy_server
from ops.recovery_archive import RecoveryError

SHA = "a" * 40


class DeployPublicTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(
            os.environ,
            {
                "AULAS_PUBLIC_SSH_HOST": "deploy@vm.example",
                "AULAS_PUBLIC_URL": "https://aulas.example.com",
            },
        )
        env.start()
        self.addCleanup(env.stop)

    def invoke(self, argv, results=None):
        output = io.StringIO()
        with (
            patch.object(
                deploy_client, "run", side_effect=results or [SHA.encode(), b"", b"ready\n"]
            ) as run,
            patch.object(deploy_client.public_probe, "main", return_value=0) as probe,
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            status = deploy_client.main(argv)
        return status, run, probe, output.getvalue()

    def test_missing_or_root_host_refuses_before_git_or_ssh(self):
        for host in ("", "root@vm.example", "deploy@vm;evil", "-Fconfig@host", "user@-host"):
            with self.subTest(host=host), patch.dict(os.environ, {"AULAS_PUBLIC_SSH_HOST": host}):
                status, run, _, _ = self.invoke([SHA])
                self.assertEqual(status, 1)
                run.assert_not_called()

    def test_sha_validation_and_ancestor_failure_never_contacts_ssh(self):
        for arg in ("main", "HEAD", "a;touch", "a" * 41):
            self.assertEqual(self.invoke([arg])[0], 1)
        status, run, _, _ = self.invoke([SHA], [SHA.encode(), RecoveryError("not ancestor")])
        self.assertEqual(status, 1)
        self.assertFalse(any(c.args[0][0] == "ssh" for c in run.call_args_list))

    def test_dry_run_checks_commit_but_does_not_contact_remote_or_probe(self):
        status, run, probe, _ = self.invoke(["--dry-run", SHA])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 2)
        probe.assert_not_called()

    def test_success_sends_only_fixed_deploy_command_and_runs_public_probe(self):
        status, run, probe, _ = self.invoke([SHA])
        self.assertEqual(status, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[-2:], ["deploy@vm.example", f"deploy {SHA}"])
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertGreater(run.call_args.kwargs["timeout"], 1800)
        probe.assert_called_once_with(["--base-url", "https://aulas.example.com"])

    def test_rollback_does_not_fetch_or_build(self):
        status, run, _, _ = self.invoke(["--rollback"], [b"rollback-ready\n"])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-1], "rollback")

    def test_remote_failure_is_sanitized_and_stops_public_probe(self):
        status, _, probe, output = self.invoke(
            [SHA], [SHA.encode(), b"", RuntimeError("secret learner text")]
        )
        self.assertEqual(status, 1)
        self.assertNotIn("secret learner", output)
        probe.assert_not_called()

    def test_forced_command_rejects_shell_substitution_arguments_and_uploads(self):
        self.assertEqual(deploy_server.parse(f"deploy {SHA}"), ("deploy", SHA))
        self.assertEqual(deploy_server.parse("rollback"), ("rollback", None))
        for command in (
            "",
            "adopt",
            "sh",
            "scp -t /tmp/file",
            f"deploy {SHA}; id",
            f"deploy {SHA}\n",
            "rollback --build",
            "deploy $(id)",
        ):
            with self.subTest(command=command), self.assertRaises(RecoveryError):
                deploy_server.parse(command)
