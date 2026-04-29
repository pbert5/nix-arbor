import subprocess
import unittest
from unittest import mock

from backend.tape.runner import TapeCommandRunner


class TapeCommandRunnerTests(unittest.TestCase):
    def test_run_requests_utf8_replacement_for_command_output(self):
        runner = TapeCommandRunner()

        completed = subprocess.CompletedProcess(
            args=["ltfsck", "/dev/sg1"],
            returncode=0,
            stdout="ok",
            stderr="",
        )

        with mock.patch("backend.tape.runner.subprocess.run", return_value=completed) as run_mock:
            result = runner.run(["ltfsck", "/dev/sg1"], name="ltfsck")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok")
        run_mock.assert_called_once_with(
            ["ltfsck", "/dev/sg1"],
            input=None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=runner.timeouts["ltfsck"],
        )

    def test_run_decodes_timeout_bytes_with_replacement(self):
        runner = TapeCommandRunner()

        with mock.patch(
            "backend.tape.runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["ltfsck", "/dev/sg1"],
                timeout=1,
                output=b"bad\xd0bytes",
                stderr=b"warn\xff",
            ),
        ):
            result = runner.run(["ltfsck", "/dev/sg1"], timeout=1, name="ltfsck")

        self.assertTrue(result.timed_out)
        self.assertEqual(result.stdout, "bad�bytes")
        self.assertEqual(result.stderr, "warn�")


if __name__ == "__main__":
    unittest.main()