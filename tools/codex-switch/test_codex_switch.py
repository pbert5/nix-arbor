from __future__ import annotations

import base64
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("codex-switch.py")
SPEC = importlib.util.spec_from_file_location("codex_switch", MODULE_PATH)
assert SPEC and SPEC.loader
codex_switch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codex_switch)


def token(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.sig"


def auth(email: str, account_id: str) -> dict:
    return {
        "tokens": {
            "id_token": token(
                {
                    "email": email,
                    "sub": f"sub-{account_id}",
                    "https://api.openai.com/auth": {
                        "chatgpt_plan_type": "plus",
                        "user_id": f"user-{account_id}",
                    },
                }
            ),
            "access_token": "access",
            "refresh_token": "refresh",
            "account_id": account_id,
        }
    }


class CodexSwitchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        self.old_codex_home = os.environ.get("CODEX_HOME")
        os.environ["HOME"] = self.tmp.name
        os.environ.pop("CODEX_HOME", None)

    def tearDown(self) -> None:
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home
        if self.old_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self.old_codex_home
        self.tmp.cleanup()

    @property
    def root(self) -> Path:
        return Path(self.tmp.name)

    def test_add_current_and_switch(self):
        codex_dir = self.root / ".codex"
        codex_dir.mkdir()
        (codex_dir / "auth.json").write_text(
            json.dumps(auth("user@example.com", "acct-1")),
            encoding="utf-8",
        )

        self.assertEqual(codex_switch.main(["add-current", "first", "--activate"]), 0)
        profiles = json.loads((self.root / ".codex-switch" / "profiles.json").read_text())
        self.assertEqual(profiles["profiles"][0]["name"], "first")
        self.assertEqual(profiles["profiles"][0]["email"], "user@example.com")

        imported = self.root / "second-auth.json"
        imported.write_text(json.dumps(auth("user@example.com", "acct-2")), encoding="utf-8")
        self.assertEqual(codex_switch.main(["add-current", "second", "--auth-file", str(imported)]), 0)
        self.assertEqual(codex_switch.main(["switch", "second"]), 0)

        active_auth = json.loads((codex_dir / "auth.json").read_text())
        self.assertEqual(active_auth["tokens"]["account_id"], "acct-2")
        active_state = json.loads(
            (self.root / ".codex-switch" / "active-profiles" / "default.json").read_text()
        )
        self.assertTrue(active_state["profileId"])

    def test_prepare_login_removes_auth(self):
        codex_dir = self.root / ".codex"
        codex_dir.mkdir()
        (codex_dir / "auth.json").write_text("{}", encoding="utf-8")

        self.assertEqual(codex_switch.main(["prepare-login"]), 0)
        self.assertFalse((codex_dir / "auth.json").exists())


if __name__ == "__main__":
    unittest.main()
