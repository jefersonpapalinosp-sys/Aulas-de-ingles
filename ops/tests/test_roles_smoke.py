"""Guardas do ensaio de privilégios; nenhum comando Docker/SQL real."""

import io
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ops import roles, roles_smoke
from ops.recovery_archive import RecoveryError


class RolesSmokeTests(unittest.TestCase):
    def test_forbidden_requires_insufficient_privilege_not_any_failure(self):
        def denied(stderr):
            error = RecoveryError("synthetic")
            error.__cause__ = subprocess.CalledProcessError(1, "psql", stderr=stderr)
            return error

        info = ({"Id": "synthetic"}, "lab", "admin")
        with patch.object(roles, "sql", side_effect=denied(b"ERROR: 42501: denied")) as sql:
            roles_smoke.forbidden(info, "aulas_runtime", "CREATE ROLE forbidden")
        self.assertTrue(sql.call_args.args[1].startswith("\\set VERBOSITY verbose\n"))
        for stderr in (None, b"08006: connection lost", "42501", b""):
            with (
                self.subTest(stderr=stderr),
                patch.object(roles, "sql", side_effect=denied(stderr)),
                self.assertRaises(RecoveryError),
            ):
                roles_smoke.forbidden(info, "aulas_runtime", "unused")
        with (
            patch.object(roles, "sql", return_value=b""),
            self.assertRaisesRegex(RecoveryError, "proibida foi permitida"),
        ):
            roles_smoke.forbidden(info, "aulas_runtime", "unused")

    def test_global_privilege_stops_before_mutations(self):
        with (
            patch.object(roles, "target", return_value=({}, "lab", "admin")),
            patch.object(roles, "sql", return_value=b"[true,false,false,false,false]"),
            patch.object(roles_smoke, "forbidden") as forbidden,
            patch.object(roles, "lab_run") as lab_run,
            self.assertRaisesRegex(RecoveryError, "poderes globais"),
        ):
            roles_smoke.main()
        forbidden.assert_not_called()
        lab_run.assert_not_called()

    def test_dump_requires_content_before_success(self):
        for content in (b"synthetic-dump", b""):
            with self.subTest(nonempty=bool(content)):
                output = io.StringIO()

                def docker(*args, content=content, **kwargs):
                    self.assertEqual(args[2], "synthetic-container")
                    if "pg_dump" in args:
                        self.assertIn("aulas_backup", args)
                        kwargs["stdout"].write(content)
                    else:
                        self.assertIn("pg_restore", args)
                        self.assertIn("--list", args)
                        self.assertEqual(kwargs["stdin"].read(), content)
                    return b""

                with (
                    patch.object(
                        roles, "target",
                        return_value=({"Id": "synthetic-container"}, "lab", "admin"),
                    ),
                    patch.object(roles, "sql", return_value=b"[false,false,false,false,false]"),
                    patch.object(roles_smoke, "forbidden"),
                    patch.object(roles, "lab_run") as lab_run,
                    patch.object(roles_smoke.recovery, "docker", side_effect=docker) as command,
                    redirect_stdout(output),
                ):
                    if content:
                        roles_smoke.main()
                    else:
                        with self.assertRaisesRegex(RecoveryError, "Dump de leitura vazio"):
                            roles_smoke.main()
                self.assertEqual(command.call_count, 2 if content else 1)
                lab_run.assert_any_call("runtime", "python", "/tools/roles_app_smoke.py")
                lab_run.assert_any_call("worker", "python", "/tools/roles_dialogue_smoke.py")
                self.assertEqual("Papéis aprovados" in output.getvalue(), bool(content))
