# Private OCI registry

The r640 profile enables `arbor.ci.privateRegistry`. This adds a local CNCF
Distribution registry, two loopback-only Nginx gateways, and an opt-in Tailscale
Serve endpoint. Tailscale Serve terminates HTTPS on ports 443 and 8443, proxies
to the loopback gateways, and provisions/renews the host's MagicDNS
certificate. Clients validate the normal
Tailscale HTTPS certificate. Do not use an insecure registry setting or expose
the listener through Funnel, a public reverse proxy, or a router port forward.

The client hostname is
`r640-0.<tailnet-DNS-suffix>.ts.net`. The pull endpoint uses HTTPS port 443;
the push endpoint uses HTTPS port 8443. `<tailnet-DNS-suffix>` is supplied
by the operator from the live tailnet and must not be committed to this public
flake. The public source contains only loopback backend addresses.

The NixOS service adds and removes only its owned Tailscale Serve ports. Before
applying it, the integration owner must inspect `tailscale serve status` and
confirm ports 443 and 8443 have no unrelated mappings; pause for operator
resolution if either is occupied. Other Serve ports must remain configured.
Restrict Tailscale policy for r640-0 ports 443 and 8443 to the trusted builder
and explicitly authorized consumer machines; do not grant wildcard tailnet
access.

## Authentication and image names

The gateway reads two independent runtime htpasswd files:

* `/run/secrets/private-oci-registry/pull.htpasswd` for pull-only clients.
  The reader gateway accepts only GET and HEAD.
* `/run/secrets/private-oci-registry/push.htpasswd` for trusted image builders.
  The writer gateway permits the registry API methods required for push and
  pull.

The operator provisions both files through the approved runtime secret
provider. They must be readable by the Nginx worker and inaccessible to
untrusted users. Nginx and the Tailscale Serve configuration fail closed when
either file is missing. Never put a password, htpasswd file, token, or private
key in Nix source or a derivation input. Create credentials out-of-band with a
password manager and an interactive `htpasswd -B` command; distribute only the
pull credential to consumer machines. Rotate credentials by replacing the
runtime files and restarting Nginx.

Use immutable image tags under `ci/<repository>/<full-commit-sha>` and
BuildKit cache references under `buildkit/<builder-or-repository>`. Record
the `Docker-Content-Digest` returned by push and consume images by digest:

```text
r640-0.<tailnet-DNS-suffix>.ts.net/ci/<repository>@sha256:<digest>
```

For builds, configure the authorized builder with
`r640-0.<tailnet-DNS-suffix>.ts.net:8443` and push/pull credentials.
Authorized machines use the default port (443), the pull credential, and the
digest reference. The cache namespace is separate from immutable artifacts.
Do not give public-fork jobs tailnet connectivity or registry credentials.

## Storage, retention, and recovery

All registry blobs live in `/mypool/oci-registry/data`. A dedicated oneshot
checks that `/mypool` is a mountpoint before creating the directory, and both
registry and Nginx require it. The registry binds only to loopback on port
5100; the gateways bind only to loopback on ports 5101 and 5102. The pool
failure path therefore fails closed instead of creating a shadow directory
on the root filesystem. Existing `/mypool/docker_data` and `/mypool/nix-build`
are not changed.

Keep release artifacts for at least 180 days after the source commit is no
longer supported. Keep mutable BuildKit cache tags for at most 30 days. Before
removing a manifest, record its repository, tag, digest, and age, and confirm
that no supported release or active builder references it. Distribution
deletion is enabled, while the upstream scheduled garbage collector is
disabled because it has no retention policy. Use a maintenance window and
inspect a dry run before deleting unreferenced data:

```sh
sudo systemctl stop nginx docker-registry
sudo systemctl start private-oci-registry-gc-dry-run.service
sudo journalctl -u private-oci-registry-gc-dry-run.service
```

After a reviewed dry run and deliberate tag deletion, copy the command shown
by `systemctl cat private-oci-registry-gc-dry-run.service`, remove only
`--dry-run`, and run it as `docker-registry` while both services remain
stopped. Do not run concurrent pushes during garbage collection. The root
module keeps destructive GC manual; the operator records the dry-run and
deletion results in the maintenance log.

Back up the registry data directory while the service is stopped or from a
consistent ZFS snapshot created by the operator. Preserve the relative
directory layout and ownership when restoring to `/mypool/oci-registry/data`.
Restore the runtime auth files independently from the approved secret
provider, verify the pool mount before starting, then start the registry,
Nginx, and Tailscale Serve in that order. Confirm `/v2/` with the reader
credential and pull a known image by recorded digest. Recovery must not create
or import a ZFS dataset automatically.

## Live acceptance boundary

The software interface is implemented declaratively, but host integration
requires WS-I/operator work: verify the current Tailscale Serve ports and
hostname, set the narrow Tailscale access policy, provision the two runtime credentials, and
exercise TLS and pull/push access from separate authorized clients. A denied
unauthenticated request, a rejected reader push, a digest-equal pull, restart
persistence, and a reviewed GC dry run must be recorded before claiming live
acceptance. Roll back by disabling the Nix option and applying the previous
system generation; remove only the HTTPS 443 and 8443 Tailscale Serve mappings
owned by this module, preserving every other Serve port.
