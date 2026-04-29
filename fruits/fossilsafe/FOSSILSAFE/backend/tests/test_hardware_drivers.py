"""Hardware-focused regression tests for tape controllers and helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.library_manager import LibraryManager
from backend.tape_controller import TapeLibraryController, TapeLoadError
from backend.utils.hardware import parse_tape_alerts


class TestTapeControllers:
    """Logic for low-level LTO and MTX command parsing."""

    def test_parse_tape_alerts_deduplicates_known_and_unknown_codes(self):
        alerts = parse_tape_alerts(
            "\n".join(
                [
                    "TapeAlert [0x01]: Read warning",
                    "TapeAlert [0x01]: Read warning",
                    "TapeAlert [0x1f]: Hardware failure",
                    "TapeAlert [0x99]: Vendor specific",
                ]
            )
        )

        assert [alert["code"] for alert in alerts] == [1, 31, 153]
        assert alerts[0]["name"] == "Read Warning"
        assert alerts[1]["severity"] == "critical"
        assert alerts[2]["name"] == "Unknown Alert (153)"

    def test_drive_only_load_rejects_hardware_barcode_mismatch(self):
        controller = TapeLibraryController(device="/dev/nst0", changer=None, config={}, state={})
        controller.drive_only_mode = True

        with patch.object(controller, "_get_drive_barcode", return_value="REAL001"):
            with pytest.raises(TapeLoadError, match="Barcode mismatch"):
                controller.load_tape("USER001")

    def test_drive_only_load_accepts_manual_tape_when_mam_is_unavailable(self):
        controller = TapeLibraryController(device="/dev/nst0", changer=None, config={}, state={})
        controller.drive_only_mode = True

        with patch.object(controller, "_get_drive_barcode", return_value=None):
            assert controller.load_tape("MANUAL01") is True

        assert controller.manual_tape_barcode == "MANUAL01"
        assert controller.get_current_tape()["barcode"] == "MANUAL01"

    def test_identify_drive_mapping_uses_detected_barcode_match(self):
        controller = TapeLibraryController(device="/dev/nst0", changer="/dev/sg1", config={}, state={})
        controller.drive_only_mode = False
        controller.move_tape = MagicMock(return_value=True)

        with patch(
            "backend.tape_controller.discover_devices",
            return_value=(
                [
                    SimpleNamespace(path="/dev/nst0"),
                    SimpleNamespace(path="/dev/nst1"),
                ],
                None,
            ),
        ), patch.object(controller, "_get_drive_barcode", side_effect=["OTHER01", "MATCH01"]):
            matched = controller.identify_drive_mapping(1, "MATCH01")

        assert matched == "/dev/nst1"
        controller.move_tape.assert_called_once_with(
            {"type": "slot", "value": -1},
            {"type": "drive", "value": 1},
            barcode="MATCH01",
        )

    def test_recover_library_resets_probe_state_after_force_unload(self):
        controller = TapeLibraryController(device="/dev/nst0", changer="/dev/sg1", config={}, state={})
        controller._probe_failures = 4
        controller._probe_failure_timestamps.extend([1.0, 2.0, 3.0])
        controller._auto_correct_attempted = True
        controller.library_error = "changer offline"
        controller._last_probe = {"status": "bad"}
        controller._last_mtx_check = 99.0
        controller._state_changed_at = 77.0

        with patch.object(controller, "force_unload_tape", return_value=True), patch.object(
            controller,
            "_check_library_status",
            return_value=True,
        ):
            result = controller.recover_library(drive=0, force_unload=True)

        assert result["force_unload_attempted"] is True
        assert result["force_unload_ok"] is True
        assert result["library_online"] is True
        assert controller._probe_failures == 0
        assert list(controller._probe_failure_timestamps) == []
        assert controller.library_error is None


class TestLibraryManagement:
    """Logic for robotics (changer) movement and inventory."""

    def test_library_manager_converts_drive_device_lists_to_indexed_mapping(self):
        mock_db = MagicMock()

        with patch(
            "backend.library_manager.load_config",
            return_value={
                "libraries": [
                    {
                        "id": "lib-a",
                        "drive_devices": ["/dev/nst0", "/dev/nst1"],
                        "changer": "/dev/sg0",
                    }
                ]
            },
        ), patch("backend.library_manager.load_state", return_value={}), patch(
            "backend.library_manager.TapeLibraryController"
        ) as mock_controller:
            manager = LibraryManager(mock_db)
            manager.initialize()

        assert "lib-a" in manager.controllers
        assert mock_controller.call_args.kwargs["device"] == {0: "/dev/nst0", 1: "/dev/nst1"}
