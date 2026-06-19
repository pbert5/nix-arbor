from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ChangerInventory:
    changer_device: str | None
    drive_count: int | None
    slot_count: int | None
    import_export_count: int | None
    drives: list[dict[str, Any]]
    slots: list[dict[str, Any]]
    raw_status: str | None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_changer_inventory(changer_device: str | None) -> ChangerInventory:
    if changer_device is None:
        return ChangerInventory(
            changer_device=None,
            drive_count=None,
            slot_count=None,
            import_export_count=None,
            drives=[],
            slots=[],
            raw_status=None,
            error="No changer device is configured.",
        )

    try:
        completed = subprocess.run(
            ["mtx", "-f", changer_device, "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ChangerInventory(
            changer_device=changer_device,
            drive_count=None,
            slot_count=None,
            import_export_count=None,
            drives=[],
            slots=[],
            raw_status=None,
            error=str(exc),
        )

    raw_status = completed.stdout
    if completed.returncode != 0:
        return ChangerInventory(
            changer_device=changer_device,
            drive_count=None,
            slot_count=None,
            import_export_count=None,
            drives=[],
            slots=[],
            raw_status=raw_status,
            error=completed.stderr.strip() or f"mtx exited with {completed.returncode}",
        )

    return parse_mtx_status(changer_device, raw_status)


def parse_mtx_status(changer_device: str | None, raw_status: str) -> ChangerInventory:
    drive_count = None
    slot_count = None
    import_export_count = None
    drives: list[dict[str, Any]] = []
    slots: list[dict[str, Any]] = []

    for line in raw_status.splitlines():
        header = re.search(
            r":(?P<drives>\d+) Drives, (?P<slots>\d+) Slots(?: \( (?P<ie>\d+) Import/Export \))?",
            line,
        )
        if header:
            drive_count = int(header.group("drives"))
            slot_count = int(header.group("slots"))
            import_export_count = int(header.group("ie") or 0)
            continue

        drive = re.search(
            r"Data Transfer Element (?P<index>\d+):(?P<state>Empty|Full)(?P<rest>.*)",
            line,
        )
        if drive:
            rest = drive.group("rest")
            drives.append(
                {
                    "index": int(drive.group("index")),
                    "state": drive.group("state").lower(),
                    "barcode": _volume_tag(rest),
                    "source_slot": _loaded_source_slot(rest),
                    "raw": line.strip(),
                }
            )
            continue

        slot = re.search(
            r"Storage Element (?P<slot>\d+)(?P<ie> IMPORT/EXPORT)?:"
            r"(?P<state>Empty|Full)(?P<rest>.*)",
            line,
        )
        if slot:
            slots.append(
                {
                    "slot": int(slot.group("slot")),
                    "import_export": slot.group("ie") is not None,
                    "state": slot.group("state").lower(),
                    "barcode": _volume_tag(slot.group("rest")),
                    "raw": line.strip(),
                }
            )

    return ChangerInventory(
        changer_device=changer_device,
        drive_count=drive_count,
        slot_count=slot_count,
        import_export_count=import_export_count,
        drives=drives,
        slots=slots,
        raw_status=raw_status,
    )


def _volume_tag(text: str) -> str | None:
    match = re.search(r"VolumeTag\s*=\s*(?P<tag>\S+)", text)
    if match is None:
        return None
    return match.group("tag").strip()


def _loaded_source_slot(text: str) -> int | None:
    match = re.search(r"Storage Element (?P<slot>\d+) Loaded", text)
    if match is None:
        return None
    return int(match.group("slot"))


def barcode_generation(barcode: str) -> str | None:
    match = re.search(r"(L\d+)$", barcode)
    if match is None:
        return None
    return match.group(1)


def is_allowed_barcode(barcode: str, allowed_generations: list[str]) -> bool:
    generation = barcode_generation(barcode)
    return generation is not None and generation in allowed_generations


def sg_device_for_st_device(st_device: str) -> str | None:
    stream_device = _stream_device_for_non_rewinding(st_device)
    try:
        completed = subprocess.run(
            ["lsscsi", "-g"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None

    fallback = None
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] != "tape":
            continue
        if not parts[-1].startswith("/dev/sg"):
            continue
        if fallback is None:
            fallback = parts[-1]
        if len(parts) >= 2 and parts[-2] == stream_device:
            return parts[-1]
    return fallback


def _stream_device_for_non_rewinding(st_device: str) -> str:
    resolved = str(Path(st_device).resolve())
    if resolved.startswith("/dev/nst"):
        return "/dev/st" + resolved.removeprefix("/dev/nst")
    return resolved
