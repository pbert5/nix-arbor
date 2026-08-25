import json
import socket
from pathlib import Path

token = Path("/run/arbor-test/registry.token").read_text().strip()
event = {"recordId": "transport-local-root-b", "recordVersion": 1, "kind": "transport-acceptance"}
request = {"operation": "append", "stream": "registry", "token": token, "event": event}
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.connect("/run/arbor-registryd/registry.sock")
    connection.sendall((json.dumps(request) + "\n").encode())
    connection.shutdown(socket.SHUT_WR)
    response = b""
    while not response.endswith(b"\n"):
        chunk = connection.recv(65536)
        if not chunk:
            break
        response += chunk
result = json.loads(response)
assert result.get("ok") is True, result
print(json.dumps(result))
