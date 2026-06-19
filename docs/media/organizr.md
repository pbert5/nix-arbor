# Organizr

Organizr is modeled as the `organizr` fruit and currently selected by
`t320-0` in [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix).
The listen surface is declared in
[`inventory/ports.nix`](/work/flake/inventory/ports.nix) as
`0.0.0.0:9983`, with `http://t320-0:9983` as the operator-facing URL.

## Runtime

The fruit uses the official `ghcr.io/organizr/organizr:latest` container through
`virtualisation.oci-containers` with Podman as the backend. This matches the
upstream container flow: the image provides the web server and PHP runtime, then
clones the Organizr application into the mounted config directory on first
start.

The upstream PHP prerequisite notes call out PHP-FPM plus SQLite, XML, ZIP,
OpenSSL, and cURL support. Those dependencies are supplied inside the official
container for this deployment, so the host only needs Podman, the persistent
state directory, and the published port.

## Configuration

Host-specific knobs live under `org.organizr` in host inventory:

```nix
org.organizr = {
  openFirewall = true;
  stateDir = "/var/lib/organizr";
  puid = 911;
  pgid = 911;
};
```

`openFirewall` defaults to `true` when the fruit is attached, so the configured
TCP port is reachable from the network. Set it to `false` for a loopback-only or
reverse-proxy-only deployment.

The container defaults to `PUID=911` and `PGID=911`. Do not set either value to
`0`; the PHP-FPM pool inside the upstream image refuses to start as root, which
leaves nginx serving `502 Bad Gateway`.

The state directory itself is mode `0755` so the non-root web/PHP process inside
the container can traverse `/config`. Sensitive bootstrap material lives below
`/var/lib/organizr/secrets`, which remains root-only.

First-time setup is handled by the `organizr-setup` oneshot service. It posts
the wizard values once, choosing the `personal` install type and creating the
initial admin from user1's inventory record. The NixOS password hash is used only
as seed material because Organizr stores PHP bcrypt hashes internally and cannot
verify the system yescrypt hash directly.

The derived initial Organizr password is stored root-only at:

```bash
/var/lib/organizr/secrets/admin-password
```

After Organizr creates `www/organizr/data/config/config.php`, the setup service
skips future runs.

## Local Smoke Test

Run a disposable instance without switching the host:

```bash
nix run .#organizr-test
```

The test binds `127.0.0.1:19983`, creates a temporary `/config` directory, waits
for HTTP to answer, and cleans up the container and rootless Podman-owned test
state when it exits.
