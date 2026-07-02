import hashlib
import json
import math
import unicodedata


class CanonicalJSONError(ValueError):
    pass


def _validate(value, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJSONError(f"{path}: non-finite numbers are forbidden")
        raise CanonicalJSONError(f"{path}: floating-point numbers are forbidden")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise CanonicalJSONError(f"{path}: strings must be NFC-normalized")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError(f"{path}: object keys must be strings")
            _validate(key, f"{path}.<key>")
            _validate(item, f"{path}.{key}")
        return
    raise CanonicalJSONError(f"{path}: unsupported value type {type(value).__name__}")


def canonical_bytes(value) -> bytes:
    """Serialize the registry's integer-only RFC 8785-compatible JSON profile."""
    _validate(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_sha256(value) -> str:
    return sha256_bytes(canonical_bytes(value))


def without_fields(record: dict, *fields: str) -> dict:
    omitted = set(fields)
    return {key: value for key, value in record.items() if key not in omitted}


def signing_payload(record: dict) -> bytes:
    return canonical_bytes(without_fields(record, "signature", "signatures"))


def event_hash_payload(event: dict) -> dict:
    return without_fields(event, "eventHash", "signature", "signatures")


def event_payload(event: dict) -> dict:
    fields = [
        "clusterId",
        "subject",
        "generation",
        "public",
        "privateDelivery",
        "burned",
    ]
    return {field: event.get(field) for field in fields if event.get(field) is not None}
