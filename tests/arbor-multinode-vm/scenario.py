"""Bootstrap the VM registry through the packaged operator boundary."""

import json
import subprocess
from pathlib import Path


ROOT = Path("/run/arbor-test")
CONFIG = ROOT / "registryctl.json"


def ctl(*args: str) -> dict:
    command = ["arbor-registryctl", "--config", str(CONFIG), "--format", "json", *args]
    return json.loads(subprocess.check_output(command, text=True))


def main() -> None:
    keys = ROOT / "keys"
    authorities = ROOT / "bootstrap-authorities.json"
    ROOT.mkdir(mode=0o700, exist_ok=True)
    keys.mkdir(mode=0o700, exist_ok=True)
    authorities.write_text("{}\n", encoding="utf-8")
    CONFIG.write_text(json.dumps({
        "stateDir": str(ROOT / "accepted"),
        "transportSocket": "/run/arbor-registryd/registry.sock",
        "transportTokenFile": str(ROOT / "registry.token"),
        "bootstrapAuthoritiesFile": str(authorities),
        "identityDir": str(keys),
        "providerCursorFile": str(ROOT / "provider-cursor.json"),
        "authorityIssuers": ["root-a"],
    }, sort_keys=True) + "\n", encoding="utf-8")
    for issuer in ("root-a", "child", "grandchild"):
        result = ctl("keygen", issuer)
        (ROOT / f"{issuer}.public").write_text(result["publicKey"] + "\n", encoding="ascii")
        if issuer == "root-a":
            authorities.write_text(json.dumps({"root-a": result["publicKey"]}) + "\n", encoding="utf-8")
    root_public = json.loads(authorities.read_text())["root-a"]
    for identity in ("root-a", "child", "grandchild"):
        public_key = (ROOT / f"{identity}.public").read_text().strip()
        result = ctl("identity-generation", identity, public_key, "--issuer", "root-a")
        assert result["status"] == "accepted", result
    print(json.dumps({"accepted": len(ctl("accepted")), "status": ctl("status"), "root": root_public}, sort_keys=True))


if __name__ == "__main__":
    main()
