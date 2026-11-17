#!/usr/bin/env python3
"""Exercise the real locked Manager through each checkout-local launcher."""
import hashlib
import json
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading

TOOLS = Path(__file__).resolve().parent


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    return hashlib.sha256(data.encode()).hexdigest()


def run(name, *args, ok=True):
    result = subprocess.run([str(TOOLS / name), *map(str, args)], cwd="/tmp", text=True, capture_output=True)
    assert (result.returncode == 0) == ok, (name, result.stdout, result.stderr)
    return result.stdout + result.stderr


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        request = json.loads(self.rfile.readline())
        self.wfile.write((json.dumps({"ok": True, "result": {"operation": request["operation"]}}) + "\n").encode())


with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp)
    snapshot = {"format": "arbor-manager/deployment-snapshot", "version": 1,
                "snapshot": {"roots": ["api"], "selector": "local", "selected": ["api"],
                             "excluded": [], "nodes": {"api": {"hostname": "api.example"}}},
                "plan": {"backend": "direct", "phases": []}, "acknowledgement": None}
    snapshot["snapshotDigest"] = digest(snapshot["snapshot"])
    snapshot["digest"] = digest(snapshot)
    file = path / "snapshot.json"
    file.write_text(json.dumps(snapshot))
    sock = path / "network.sock"
    with socketserver.UnixStreamServer(str(sock), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        assert "api" in run("nodes", "--snapshot", file, "--format", "names")
        assert "api.example" in run("inspect", "--snapshot", file, "--name", "api")
        assert "snapshotDigest" in run("snapshot", "--snapshot", file)
        assert "backend" in run("plan", "--snapshot", file)
        assert "backend=direct" in run("plan", "--snapshot", file, "--format", "text")
        assert "risks=[]" in run("plan", "--snapshot", file, "--format", "text")
        assert '"operation": "status"' in run("network", "status", "--socket", sock)
        assert "snapshot: valid" in run("status", "--snapshot", file, "--socket", sock)
        server.shutdown()
        thread.join()
    assert "not supplied" in run("status", ok=False)
    assert "--snapshot is required" in run("nodes", ok=False)
    assert "cannot connect" in run("network", "status", "--socket", path / "missing", ok=False)
    snapshot["snapshot"]["selector"] = "tampered"
    file.write_text(json.dumps(snapshot))
    assert "snapshotDigest does not match" in run("snapshot", "--snapshot", file, ok=False)
    assert "Usage:" in run("plan", "--help")
print("Arbor tools: all checks passed")
