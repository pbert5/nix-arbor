import json
import os
import tempfile
import unittest

from backend.config_store import load_config, update_config


class ConfigStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmpdir.name, "config.json")

        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "auth": {
                        "native_2fa_enabled": False,
                        "session_timeout_minutes": 30,
                    },
                    "tape": {
                        "changer_device": "/dev/changer0",
                        "timeouts": {
                            "mtx_status": 15,
                        },
                    },
                },
                handle,
                indent=2,
                sort_keys=True,
            )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_update_config_recursively_merges_nested_updates(self):
        updated = update_config(
            {
                "tape": {
                    "mail_slot_detected": True,
                    "timeouts": {
                        "mtx_inventory": 300,
                    },
                }
            },
            path=self.config_path,
        )

        self.assertFalse(updated["auth"]["native_2fa_enabled"])
        self.assertEqual(updated["auth"]["session_timeout_minutes"], 30)
        self.assertEqual(updated["tape"]["changer_device"], "/dev/changer0")
        self.assertTrue(updated["tape"]["mail_slot_detected"])
        self.assertEqual(updated["tape"]["timeouts"]["mtx_status"], 15)
        self.assertEqual(updated["tape"]["timeouts"]["mtx_inventory"], 300)

        reloaded = load_config(self.config_path)
        self.assertEqual(reloaded, updated)


if __name__ == "__main__":
    unittest.main()