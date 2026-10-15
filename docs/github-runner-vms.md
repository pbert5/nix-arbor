# Isolated GitHub Actions runner VMs

Nix Arbor exposes an opt-in repository-scoped runner inventory through
`arbor.ci.runners`. `r640-0` declares the repositories `pbert5/nix-arbor`,
`pbert5/meta_bal`, and `pbert5/simple-evolver`; each remains disabled until an
operator explicitly sets its `enable` option and provisions that repository's
runtime credential. No wildcard or organization-wide enrollment is supported.

Each enabled repository gets its own NixOS MicroVM managed by the pinned
`microvm.nix` input. QEMU uses user-mode networking without forwarded host
ports. The host QEMU service is denied access to loopback, link-local, private,
shared, and multicast address ranges by systemd's cgroup IP filter. This keeps
the VM away from services on the host and local networks while allowing normal
public GitHub access. If the registry is hosted on a private address, an
operator can add exact address CIDRs to that repository's `allowedNetworks`
after the registry workstream defines the endpoint. `allowedNetworks` is an
explicit systemd IP allow rule and can override the default private-range
denials, so only add the registry's resolved address range after independent
review. Add host and cluster CIDRs that are not covered by the built-in
private/link-local ranges to `blockedNetworks`.

The guest owns its Docker daemon and socket. Its `/var/lib/docker` is a
32-GiB-per-runner ext4 volume under `/mypool/ci-runners`; VM startup fails
unless `/mypool` is mounted and the bounded storage directory exists. This
prevents a missing ZFS pool from silently moving runner state onto the root
filesystem. Aggregate CPU and memory limits apply through
`arbor-ci-runners.slice`, with per-VM memory and CPU limits as well. Keep the
default one-runner ceiling until observed capacity supports an explicit
increase.

## Credentials and lifecycle

For repository key `meta_bal`, provision exactly one repository-scoped GitHub
runner credential at
`/var/lib/arbor-secrets/github-runners/meta_bal/token`. The parent directory is
restricted to root and the `microvm` service account. The token file should be
root-owned and mode `0444`; its protected parent prevents other host users from
traversing to it. The VM receives only its own directory as a read-only 9p
share mounted at `/run/arbor-ci-secrets`. Never put a token in Nix source,
NixOS options, derivations, the Nix store, logs, or workflow variables.

The NixOS runner service uses an ephemeral runner registration and re-registers
after each completed job. It runs one job at a time. Docker data and the guest
disk survive a guest reboot; removing cached state is a separate operator
maintenance action. The host VM can be safely started and stopped with:

```sh
sudo systemctl start microvm@arbor-ci-meta-bal.service
sudo systemctl status microvm@arbor-ci-meta-bal.service
sudo journalctl -u microvm@arbor-ci-meta-bal.service --no-pager
sudo systemctl stop microvm@arbor-ci-meta-bal.service
```

Inside the guest, the runner service is `github-runner-meta-bal.service`.
The inventory health probe is `systemctl is-active
microvm@arbor-ci-meta-bal.service` on the host. A missing or unreadable token
prevents guest start and registration; the token value is never copied into
the Nix store.

## Workflow trust policy

The inventory publishes the allowed event and ref policy for each repository.
GitHub does not let an on-prem runner VM enforce workflow event/ref selection
after a workflow has already targeted its labels. Every consuming workflow
must therefore gate the self-hosted job with a trusted-event and trusted-ref
condition matching the inventory, and all fork pull request checks must remain
on GitHub-hosted runners. Use GitHub-hosted runners for public forks and other
untrusted inputs. Do not give these labels to workflows that execute
unreviewed code.

For example, the self-hosted job should include a job-level condition like:

```yaml
if: >-
  github.event_name == 'push' &&
  github.ref == 'refs/heads/main'
```

Keep pull request checks on an independent GitHub-hosted job with no fallback
to these labels.

The registered labels are `self-hosted`, `linux`, `x64`, `r640-0`, and the
repository label (`nix-arbor`, `meta-bal`, or `simple-evolver`). Runner
registration and live GitHub job acceptance remain disabled until authorized
operator provisioning and WS-I host acceptance.
