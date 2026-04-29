from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from backend.config_store import load_config


DEFAULT_READ_ONLY_GENERATIONS = ["LTO-4"]


def normalize_generation(value: Optional[str]) -> str:
    if not value:
        return "Unknown"

    generation = str(value).strip().upper().replace(" ", "")
    if generation.startswith("LTO") and not generation.startswith("LTO-"):
        generation = f"LTO-{generation[3:]}"
    return generation


def get_read_only_generations(config: Optional[Dict[str, Any]] = None) -> List[str]:
    runtime_config = config or load_config()
    tape_settings = (runtime_config.get("tape", {}) or {})
    raw = tape_settings.get("read_only_generations", DEFAULT_READ_ONLY_GENERATIONS)

    if raw is None:
        raw = []
    elif isinstance(raw, str):
        raw = [raw]

    result: List[str] = []
    for item in raw:
        generation = normalize_generation(item)
        if generation != "Unknown" and generation not in result:
            result.append(generation)
    return result


def describe_write_block_reason(
    tape: Dict[str, Any],
    read_only_generations: Optional[Iterable[str]] = None,
) -> Optional[str]:
    barcode = str(tape.get("barcode") or "")
    generation = normalize_generation(tape.get("generation"))
    read_only = set(read_only_generations or get_read_only_generations())

    if tape.get("is_cleaning_tape") or barcode.startswith("CLN") or barcode.endswith("CU"):
        return "Cleaning media cannot be written"
    if generation in read_only:
        return f"{generation} media is configured as read-only legacy media"
    return None


def annotate_tape(
    tape: Dict[str, Any],
    read_only_generations: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    annotated = dict(tape)
    generation = normalize_generation(annotated.get("generation"))
    annotated["generation"] = generation

    reason = describe_write_block_reason(annotated, read_only_generations=read_only_generations)
    annotated["read_only"] = reason is not None
    annotated["writable"] = reason is None
    annotated["write_block_reason"] = reason
    return annotated


def filter_writable_tapes(
    tapes: Iterable[Dict[str, Any]],
    read_only_generations: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    readonly = list(read_only_generations or get_read_only_generations())
    return [
        annotated
        for annotated in (annotate_tape(tape, readonly) for tape in tapes)
        if annotated.get("writable")
    ]
