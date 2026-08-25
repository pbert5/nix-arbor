import json
import os
from pathlib import Path

from arbor_registry_runtime import OrbitDBProvider, Runtime


root = Path("/run/arbor-test")
public_key = os.environ["ARBOR_TEST_ROOT_PUBLIC"]
provider = OrbitDBProvider(
    Path("/run/arbor-registryd/registry.sock"),
    "registry",
    token=(root / "registry.token").read_text().strip(),
)
records = [record for _, record in provider.fetch(0, 500)]
runtime = Runtime(root / "accepted-cross-guest", provider, {"root-a": public_key}, authority_issuers={"root-a"})
outcomes = runtime.ingest(records)
accepted = runtime.accepted()
assert any(record.get("recordId") == "child" for record in accepted), outcomes
print(json.dumps({"raw": len(records), "accepted": len(accepted), "materialized": len(runtime.projection())}))
runtime.close()
