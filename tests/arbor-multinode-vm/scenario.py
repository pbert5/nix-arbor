import json
import os
from pathlib import Path

from arbor_registry_runtime import OrbitDBProvider, Runtime, generate_keypair, make_identity_generation


def main():
    root = Path("/run/arbor-test")
    keys = root / "keys"
    provider = OrbitDBProvider(Path("/run/arbor-registryd/registry.sock"), "registry", token=Path("/run/arbor-test/registry.token").read_text().strip())
    root_key = generate_keypair(keys, "root-a")
    (root / "root-a.public").write_text(root_key.public_key + "\n")
    child_key = generate_keypair(keys, "child")
    grandchild_key = generate_keypair(keys, "grandchild")
    records = [
        make_identity_generation(root_key, "root-a", 1, root_key.public_key),
        make_identity_generation(root_key, "child", 1, child_key.public_key),
        make_identity_generation(root_key, "grandchild", 1, grandchild_key.public_key),
    ]
    runtime = Runtime(root / "accepted", provider, {"root-a": root_key.public_key}, authority_issuers={"root-a"})
    first = runtime.ingest(records)
    duplicate = runtime.ingest([records[0]])
    unsupported = dict(records[0], recordId="future", schema="future-schema")
    rejected = runtime.ingest([unsupported])
    assert all(item["status"] == "accepted" for item in first), first
    assert duplicate[0]["status"] == "accepted", duplicate
    assert rejected[0]["status"] == "quarantined", rejected
    assert any(item["reason"] == "unknown-schema" for item in runtime.quarantine())
    print(json.dumps({"accepted": len(runtime.accepted()), "quarantine": len(runtime.quarantine()), "duplicate": duplicate[0]["status"]}))
    runtime.close()


if __name__ == "__main__":
    main()
