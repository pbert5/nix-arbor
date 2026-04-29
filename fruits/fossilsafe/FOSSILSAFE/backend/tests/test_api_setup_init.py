import os
import tempfile
import importlib
import unittest
from unittest import mock
import json
import sys
from pathlib import Path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    import flask
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

@unittest.skipIf(not FLASK_AVAILABLE, "Flask not installed")
class ApiSetupInitTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["FOSSILSAFE_SKIP_DEP_CHECK"] = "1"
        os.environ["FOSSILSAFE_AUTOSTART_SERVICES"] = "0"
        os.environ["FOSSILSAFE_REQUIRE_API_KEY"] = "false"
        os.environ["FOSSILSAFE_DATA_DIR"] = self.tmpdir.name
        os.environ["FOSSILSAFE_CONFIG_PATH"] = os.path.join(self.tmpdir.name, "config.json")

        from backend import lto_backend_main
        importlib.reload(lto_backend_main)
        self.lto_backend_main = lto_backend_main
        
        db_path = os.path.join(self.tmpdir.name, "test.db")
        lto_backend_main._init_db(db_path)
        
        self.app = lto_backend_main.create_app(
            {"TESTING": True, "DB_PATH": db_path, "WTF_CSRF_ENABLED": False},
            autostart_services=False,
        )
        self.client = self.app.test_client()

        # Create admin user for testing
        from backend.auth import get_auth_manager
        auth_manager = get_auth_manager()
        auth_manager.create_user("admin", "password123", role="admin")
        
        # Login to get token
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "password123"}
        )
        self.token = response.get_json()["data"]["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Mock tape controller
        self.mock_tape_controller = mock.Mock()
        self.lto_backend_main.tape_controller = self.mock_tape_controller
        self.app.tape_controller = self.mock_tape_controller

    def tearDown(self):
        for db_obj in {
            getattr(self.app, "db", None),
            getattr(self.lto_backend_main, "db", None),
        }:
            if db_obj is not None and hasattr(db_obj, "pool"):
                try:
                    db_obj.pool.close_all()
                except Exception:
                    pass
        self.tmpdir.cleanup()

    def test_tape_status_endpoint(self):
        self.mock_tape_controller.inventory.return_value = [
            {"slot": 1, "barcode": "T00001L6", "status": "available", "is_cleaning_tape": False},
            {"slot": 2, "barcode": "T00002L6", "status": "available", "is_cleaning_tape": False}
        ]
        self.mock_tape_controller.is_drive_only.return_value = False
        
        with mock.patch.object(self.app.db, 'get_tape', return_value=None):
            response = self.client.get("/api/setup/tape-status", headers=self.headers)
            print("ERROR BODY:", response.get_json())
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["data"]["count"], 2)
            self.assertEqual(data["data"]["initialized_count"], 0)
            self.assertTrue(data["data"]["has_library"])

    def test_tape_status_skips_read_only_lto4_media(self):
        self.mock_tape_controller.inventory.return_value = [
            {"slot": 1, "barcode": "T00001L4", "generation": "LTO-4", "status": "available", "is_cleaning_tape": False},
            {"slot": 2, "barcode": "T00002L6", "generation": "LTO-6", "status": "available", "is_cleaning_tape": False},
        ]
        self.mock_tape_controller.is_drive_only.return_value = False

        with mock.patch.object(self.app.db, 'get_tape', return_value=None):
            response = self.client.get("/api/setup/tape-status", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["data"]["count"], 1)
            self.assertEqual(data["data"]["tapes"][0]["barcode"], "T00002L6")
            self.assertEqual(data["data"]["skipped_read_only"][0]["barcode"], "T00001L4")

    def test_tape_init_lifecycle(self):
        # 1. Start initialization
        self.mock_tape_controller.inventory.return_value = [
            {"slot": 1, "barcode": "T00001L6", "is_cleaning_tape": False}
        ]
        self.mock_tape_controller.is_drive_only.return_value = False
        
        with mock.patch('backend.routes.setup.threading.Thread'):
            response = self.client.post("/api/setup/tape-init", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data["success"])

        # 2. Check status (mock _init_status directly in setup module)
        import backend.routes.setup as setup_mod
        setup_mod._init_status = {
            "running": True,
            "current": 1,
            "total": 5,
            "last_barcode": "T00001L6",
            "error": None,
            "complete": False
        }
        
        response = self.client.get("/api/setup/tape-init/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["current"], 1)
        self.assertTrue(data["data"]["running"])

    def test_sso_can_be_disabled_without_provider_metadata(self):
        response = self.client.post(
            "/api/auth/sso/config",
            headers=self.headers,
            json={"enabled": False}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])

        response = self.client.get("/api/auth/sso/config")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["enabled"])

    def test_system_mounts_endpoint_returns_local_and_external_destinations(self):
        restore_dir = Path(self.tmpdir.name) / "restore"

        with mock.patch('backend.routes.system._discover_host_mounts', return_value=[]), \
             mock.patch(
                 'backend.routes.system.list_external_drives',
                 return_value=[
                     {"device": "/dev/sdb1", "name": "Shuttle", "mount_point": "/media/ash/Shuttle"},
                     {"device": "/dev/sdc1", "name": "Offline", "mount_point": None},
                 ],
             ):
            response = self.client.get("/api/system/mounts", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])

        mounts = data["data"]["mounts"]
        self.assertEqual(mounts[0]["type"], "local")
        self.assertEqual(mounts[0]["path"], str(restore_dir))
        self.assertTrue(restore_dir.is_dir())

        external_mounts = [mount for mount in mounts if mount["type"] == "usb"]
        self.assertEqual(len(external_mounts), 1)
        self.assertEqual(external_mounts[0]["path"], "/media/ash/Shuttle")

if __name__ == "__main__":
    unittest.main()
