# Optional signed Nix binary cache

Nix Arbor exports `nixosModules.arbor-nix-binary-cache`, backed by the pinned
Attic source in `flake.lock` and the `attic-server` package from the root
nixpkgs input. Attic fits this stream because it stores NARs separately from
the OCI registry, signs cache metadata itself, supports scoped pull/push tokens,
and has retention-based garbage collection. `nix-serve` only serves a Nix
store and does not provide an independent authenticated writer or bounded
cache retention.

The module is opt-in. Import it in a reviewed machine composition and set
`arbor.nixBinaryCache.enable = true`. It binds to `127.0.0.1:8088` by default;
the canonical `endpoint` must be HTTPS. Integration must provide private HTTPS
ingress and set `arbor.nixBinaryCache.allowedHosts` to its exact host header.
There is no public listener in this module. Do not override the loopback bind
assertion without the #29 integration review.

Before enabling the public-pull Attic cache, #29 must install a valid TLS
certificate for the private cache hostname, publish that hostname only in the
approved private DNS, and configure ingress ACLs to admit only authorized
tailnet clients and trusted CI writers. The listener must stay loopback-only,
and the ingress must deny requests arriving outside that private ACL. Host
header filtering alone is not network access control; until those checks pass,
the cache is not accepted as private.

## Storage and secrets

Attic's SQLite database and local NAR/chunk storage live under
`/mypool/nix-binary-cache/database` and
`/mypool/nix-binary-cache/storage`. Both leaf directories are owned by the
dedicated `atticd` account and are not writable by other users. The storage preparation unit waits for ZFS import
and mount, checks `mountpoint -q /mypool`, and only then creates directories.
`atticd` has the same mount check before every start. If `mypool` is absent,
the services fail; neither unit creates `/mypool` on the root filesystem.

Provision `services.atticd.environmentFile` outside Git and the Nix store with
the required `ATTIC_SERVER_TOKEN_RS256_SECRET_BASE64` or
`ATTIC_SERVER_TOKEN_HS256_SECRET_BASE64`. The module's assertion rejects a
store path. The file must be readable by systemd root and protected as a
runtime secret. Attic's JWT key authenticates API tokens; Attic separately
generates and stores the per-cache Nix signing key in its database. Never put
either private key or an API token into Nix options, derivations, command-line
arguments recorded in logs, or a repository.

## First-time setup and roles

After the operator has reviewed and deployed the module through #29, create a
read-only cache and issue a scoped writer token on the host. Keep the
all-powerful root token private. Attic's private-cache bearer authentication
does not work with Nix's standard substituter HTTP client, so consumers use
Attic's signed read-only mode over an endpoint reachable only through private
HTTPS ingress. This does not permit public Internet access: integration must
keep the cache host on the approved private network and bind the service to
loopback behind ingress. An operator can create the cache and writer token
with:

```sh
attic login r640 https://<private-cache-host>/ <operator-token>
attic cache create r640-core --public
attic cache configure r640-core --retention-period '90 days'
attic cache info r640-core
atticadm make-token --sub ci-r640-core --validity '30 days' \
  --pull r640-core --push r640-core
atticadm make-token --sub nixos-client --validity '30 days' \
  --pull r640-core
```

Provision the writer token into its authorized runtime through the existing
secret management path. The CI writer gets only `pull` and `push` for
`r640-core`; that scope is needed for Attic's upload metadata flow. Consumers
need no Attic token: the Nix signing public key authenticates downloaded
content. Cache creation, token creation, deployment, and secret issuance are
operator actions, not performed by this module.

For CI, install the pinned `attic-client` package in the trusted job
environment, authenticate from a runtime-only token file, build an immutable
commit, and run `attic push r640-core <store-path>`. Attic's CLI needs cache
metadata access, so the writer token is limited to pull and push on this one
cache. Do not give untrusted fork
jobs the writer token. A successful push should report store paths uploaded;
record the immutable source revision, store path, and Attic cache URL in the
CI evidence.

For a read-only client, copy the private HTTPS substituter URL and public key
from `attic cache info` into that machine's NixOS configuration:

```nix
nix.settings = {
  substituters = [ "https://<private-cache-host>/r640-core" ];
  trusted-public-keys = [ "r640-core:<cache-public-key>" ];
};
```

Keep this opt-in; do not add it to global bootstrap settings. Normal Nix
substituter fallback remains available if the Attic endpoint is down. To
disable the cache, remove its substituter and trusted public key (or run
`attic use` only on clients where the cache is wanted).

## Isolated acceptance and recovery

The isolated development run for this workstream exercised a scoped-token
publish and confirmed that Attic returned HTTP 200 NAR metadata with a
signature. After restarting the isolated server, the cache metadata remained
available. A local no-substitute build also succeeded while the service was
stopped, and a connection to the machine's non-loopback address was refused
while Attic was bound to loopback. These checks did not exercise Nix client
signature acceptance: this environment's Nix daemon trusts only `root`, and
noninteractive elevation is unavailable. Do not change daemon trust to work
around this local limitation.

Before live use, the #29 integration owner must run the remaining acceptance
in an isolated VM or disposable server, never against the physical cache or
`mypool` during this workstream:

1. In an isolated VM, provision an ephemeral runtime JWT signing secret and
   create a cache. The development run published a small derivation with a
   token scoped to pull and push on that cache and confirmed signed NAR
   metadata.
2. From a separate Nix client on the approved private network, substitute the
   derivation using only the cache public signing key. Record the store path,
   key, and successful Nix signature verification. This remains unexercised
   until the client daemon trusts the configured cache key.
3. Corrupt a copied NAR or use a wrong public key and verify Nix rejects it.
4. Stop the isolated cache and verify an ordinary build succeeds through the
   normal substituters or local build fallback. A local `--no-substitute`
   build succeeded during development.
5. Restart the isolated service, verify the prior NAR metadata and client
   substitution, and collect GC logs after applying a short test retention
period. Metadata remained available after the development server restart;
client substitution and GC remain for #29.
6. In a VM with the pool mount absent, verify the storage preparation and
   Attic units fail and that no `/mypool/nix-binary-cache` directory is created
   on the root filesystem. Module evaluation confirmed the mountpoint guard
   precedes directory creation; the absent-mount service behavior remains for
   #29.
7. Verify the service configuration and Nix store contain no JWT signing
   secret or writer token. This module accepts only an external runtime file;
   secret issuance and live-store inspection remain for #29.

Rollback is `arbor.nixBinaryCache.enable = false` through the reviewed
configuration deployment, followed by restoring the previous system
generation if needed. Data remains on `/mypool/nix-binary-cache`; do not delete
it as part of rollback. Restoring the prior database and storage snapshot is
the recovery path for cache corruption. Physical integration, snapshots,
secrets, and runtime tests remain under #29 and require operator authority.

## Status

The source module and partial isolated validation are implemented in this
workstream. `nix flake check` includes an enabled-module evaluation for DB and
storage paths, service ownership, the external environment file, and both
mount guards. Nix client signature acceptance, tamper rejection, absent-mount
service behavior, GC, and private ingress ACLs still need #29 verification.
No endpoint, signing secret, cache, or physical service has been provisioned.
The configured `90 days` retention is a policy bound, not a disk quota; monitor
pool capacity and adjust retention after collecting usage evidence.
