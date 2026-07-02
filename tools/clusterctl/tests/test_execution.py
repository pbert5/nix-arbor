import argparse
import unittest
from unittest.mock import Mock, patch

from clusterctl.execution import (
    ExecutionMode,
    Privilege,
    SudoAuthorization,
    execution_mode,
    prepare_invocation,
    privileged_command,
    sudo_authorization_status,
)


class ExecutionPolicyTests(unittest.TestCase):
    def test_python_entrypoint_name_selects_check_mode(self):
        with (
            patch.dict("clusterctl.execution.os.environ", {}, clear=True),
            patch("clusterctl.execution.sys.argv", ["clusterchk"]),
        ):
            self.assertIs(execution_mode(), ExecutionMode.CHECK)

    def test_clusterchk_accepts_read_only_command(self):
        args = argparse.Namespace(
            command="identity",
            identity_command="matrix",
            fetch=True,
            status_ack=True,
        )

        prepare_invocation(args, ExecutionMode.CHECK)

        self.assertFalse(args.fetch)
        self.assertFalse(args.status_ack)

    def test_clusterchk_rejects_mutating_command(self):
        args = argparse.Namespace(command="deploy")

        with self.assertRaisesRegex(ValueError, "only permits read-only"):
            prepare_invocation(args, ExecutionMode.CHECK)

    def test_clusterplan_forces_deploy_dry_run_without_publication(self):
        args = argparse.Namespace(
            command="deploy",
            dry_run=False,
            publish_identities=True,
        )

        prepare_invocation(args, ExecutionMode.PLAN)

        self.assertTrue(args.dry_run)
        self.assertFalse(args.publish_identities)

    def test_clusterplan_rejects_command_without_safe_preview(self):
        args = argparse.Namespace(command="identity", identity_command="publish")

        with self.assertRaisesRegex(ValueError, "no safe preview"):
            prepare_invocation(args, ExecutionMode.PLAN)

    def test_local_root_wraps_only_declared_subprocess(self):
        with patch("clusterctl.execution.os.geteuid", return_value=1000):
            command = privileged_command(
                ["ssh-keygen", "-y", "-f", "/root/.ssh/id_ed25519"],
                Privilege.ROOT_LOCAL,
            )

        self.assertEqual(
            command,
            [
                "sudo",
                "--",
                "ssh-keygen",
                "-y",
                "-f",
                "/root/.ssh/id_ed25519",
            ],
        )

    def test_user_command_is_never_elevated(self):
        with patch("clusterctl.execution.os.geteuid", return_value=1000):
            command = privileged_command(
                ["nix", "flake", "check"],
                Privilege.USER,
            )

        self.assertEqual(command, ["nix", "flake", "check"])

    def test_reports_command_specific_nopasswd(self):
        runner = Mock(
            return_value=Mock(
                returncode=0,
                stdout="(root) NOPASSWD: /bin/true\n",
            )
        )
        with patch("clusterctl.execution.os.geteuid", return_value=1000):
            status = sudo_authorization_status(["/bin/true"], runner=runner)

        self.assertIs(status, SudoAuthorization.NOPASSWD)
        runner.assert_called_once()

    def test_reports_cached_credentials_when_passwordless_rule_is_absent(self):
        runner = Mock(
            side_effect=[
                Mock(returncode=0, stdout="(root) /bin/true\n"),
                Mock(returncode=0),
            ]
        )
        with patch("clusterctl.execution.os.geteuid", return_value=1000):
            status = sudo_authorization_status(["/bin/true"], runner=runner)

        self.assertIs(status, SudoAuthorization.CACHED)

    def test_reports_expected_prompt_when_noninteractive_validation_fails(self):
        runner = Mock(
            side_effect=[
                Mock(returncode=1, stdout=""),
                Mock(returncode=1),
            ]
        )
        with patch("clusterctl.execution.os.geteuid", return_value=1000):
            status = sudo_authorization_status(["/bin/true"], runner=runner)

        self.assertIs(status, SudoAuthorization.PROMPT)
