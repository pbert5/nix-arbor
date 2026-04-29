"""Tests for mtx status parsing (hardware.py)."""
from __future__ import annotations

import pytest

from tapelib.hardware import (
    ChangerInventory,
    barcode_generation,
    is_allowed_barcode,
    parse_mtx_status,
)


# ---------------------------------------------------------------------------
# Realistic TL2000 output samples
# ---------------------------------------------------------------------------

_TL2000_TWO_DRIVES = """\
  Storage Changer /dev/tape/by-id/REPLACE_ME
Data Transfer Element 0:Full (Storage Element 2 Loaded):VolumeTag = 385182L5
Data Transfer Element 1:Empty
      Storage Element 1:Empty
      Storage Element 2:Full :VolumeTag = 385182L5
      Storage Element 3:Full :VolumeTag = 430550L5
      Storage Element 4:Empty
      Storage Element 46 IMPORT/EXPORT:Empty
      Storage Element 47 IMPORT/EXPORT:Full :VolumeTag = JUNK01L4
"""

_ONE_DRIVE_EMPTY = """\
  Storage Changer /dev/sg0:1 Drives, 6 Slots ( 0 Import/Export )
Data Transfer Element 0:Empty
      Storage Element 1:Full :VolumeTag = A00001L5
      Storage Element 2:Empty
"""


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------


def test_drive_and_slot_counts_from_tl2000():
    inv = parse_mtx_status("/dev/changer", _TL2000_TWO_DRIVES)
    assert inv.drive_count == 2
    assert inv.slot_count == 47
    assert inv.import_export_count == 2


def test_drive_and_slot_counts_single_drive():
    inv = parse_mtx_status("/dev/sg0", _ONE_DRIVE_EMPTY)
    assert inv.drive_count == 1
    assert inv.slot_count == 6
    assert inv.import_export_count == 0


# ---------------------------------------------------------------------------
# Drive parsing
# ---------------------------------------------------------------------------


def test_full_drive_barcode_and_source_slot():
    inv = parse_mtx_status("/dev/changer", _TL2000_TWO_DRIVES)
    drive0 = next(d for d in inv.drives if d["index"] == 0)
    assert drive0["state"] == "full"
    assert drive0["barcode"] == "385182L5"
    assert drive0["source_slot"] == 2


def test_empty_drive():
    inv = parse_mtx_status("/dev/changer", _TL2000_TWO_DRIVES)
    drive1 = next(d for d in inv.drives if d["index"] == 1)
    assert drive1["state"] == "empty"
    assert drive1["barcode"] is None
    assert drive1["source_slot"] is None


def test_single_empty_drive():
    inv = parse_mtx_status("/dev/sg0", _ONE_DRIVE_EMPTY)
    assert len(inv.drives) == 1
    assert inv.drives[0]["state"] == "empty"


# ---------------------------------------------------------------------------
# Slot parsing
# ---------------------------------------------------------------------------


def test_full_slot_barcode():
    inv = parse_mtx_status("/dev/changer", _TL2000_TWO_DRIVES)
    slot3 = next(s for s in inv.slots if s["slot"] == 3)
    assert slot3["state"] == "full"
    assert slot3["barcode"] == "430550L5"
    assert not slot3["import_export"]


def test_empty_slot():
    inv = parse_mtx_status("/dev/changer", _TL2000_TWO_DRIVES)
    slot4 = next(s for s in inv.slots if s["slot"] == 4)
    assert slot4["state"] == "empty"
    assert slot4["barcode"] is None


def test_import_export_slot():
    inv = parse_mtx_status("/dev/changer", _TL2000_TWO_DRIVES)
    ie = next(s for s in inv.slots if s["slot"] == 46)
    assert ie["import_export"] is True
    assert ie["state"] == "empty"


def test_full_import_export_slot():
    inv = parse_mtx_status("/dev/changer", _TL2000_TWO_DRIVES)
    ie47 = next(s for s in inv.slots if s["slot"] == 47)
    assert ie47["import_export"] is True
    assert ie47["barcode"] == "JUNK01L4"


# ---------------------------------------------------------------------------
# Error / no-device paths
# ---------------------------------------------------------------------------


def test_none_changer_device_error():
    inv = parse_mtx_status(None, "")
    # parse_mtx_status itself does not produce error; that is read_changer_inventory
    # Instead, an empty parse should produce empty lists.
    assert inv.drives == []
    assert inv.slots == []


def test_as_dict_round_trips():
    inv = parse_mtx_status("/dev/changer", _TL2000_TWO_DRIVES)
    d = inv.as_dict()
    assert d["drive_count"] == 2
    assert isinstance(d["drives"], list)
    assert isinstance(d["slots"], list)


# ---------------------------------------------------------------------------
# Barcode helpers
# ---------------------------------------------------------------------------


def test_barcode_generation_lto5():
    assert barcode_generation("385182L5") == "L5"
    assert barcode_generation("430550L5") == "L5"


def test_barcode_generation_lto4():
    assert barcode_generation("JUNK01L4") == "L4"


def test_barcode_generation_short():
    assert barcode_generation("X") is None
    assert barcode_generation("") is None


def test_is_allowed_barcode():
    assert is_allowed_barcode("385182L5", ["L5"]) is True
    assert is_allowed_barcode("JUNK01L4", ["L5"]) is False
    assert is_allowed_barcode("JUNK01L4", ["L4", "L5"]) is True
