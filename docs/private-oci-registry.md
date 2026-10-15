# Private OCI registry

The r640 profile includes the registry module but leaves
`arbor.ci.privateRegistry.enable` disabled. Registry activation is an explicit
operator choice. Enabling it adds a local CNCF Distribution registry, two
loopback-only Nginx gateways, and a Tailscale Serve endpoint. Tailscale Serve
terminates HTTPS on ports 443 and 8443, proxies
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
requires operator work. Keep registry activation disabled until the operator
has completed these steps:

1. Confirm the intended rollback generation and inspect
   `tailscale serve status`. Resolve any existing mappings on ports 443 or
   8443 before proceeding; preserve every unrelated mapping.
2. Confirm `/mypool` is mounted and healthy. Provision separate reader and
   writer identities out of band with the approved secret provider, writing
   nonempty files to `/run/secrets/private-oci-registry/pull.htpasswd` and
   `/run/secrets/private-oci-registry/push.htpasswd`. Do not place credential
   values in Nix, GitHub issues, or the Nix store. Give the pull identity only
   to authorized consumers and the writer identity only to trusted builders.
3. Configure the narrow Tailscale access policy for the trusted builder and
   authorized consumer machines, then confirm the private MagicDNS hostname
   and certificate are available.
4. In the host configuration, explicitly set
   `arbor.ci.privateRegistry.enable = true`. Review the resulting system
   configuration and activation preview, including the registry, Nginx,
   Tailscale Serve, ZFS mount guards, and the two runtime credential paths.
5. During the operator-approved maintenance window, activate the reviewed
   generation. Confirm `/v2/` rejects unauthenticated requests, the reader
   credential can pull but cannot push, and the writer can push and pull over
   HTTPS from their separately authorized clients. Record a digest-equal pull,
   service restart persistence, and a reviewed GC dry run before claiming
   live acceptance.

If activation fails, return to the recorded rollback generation. Remove only
the HTTPS 443 and 8443 Tailscale Serve mappings owned by this module, preserving
every other Serve port. Do not claim live acceptance from Nix evaluation or a
dry-activation preview alone.
