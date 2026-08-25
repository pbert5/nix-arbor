import json
import socket
from pathlib import Path

token = Path("/run/arbor-test/registry.token").read_text().strip()
request = {"operation": "list", "stream": "registry", "token": token, "limit": 100}
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
print(response.decode(), end="")
