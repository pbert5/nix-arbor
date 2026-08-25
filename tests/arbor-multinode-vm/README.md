# Arbor multi-node VM acceptance

Run the heavyweight integration target with:

```sh
nix build .#arbor-multinode-vm -L
```

The test boots four isolated NixOS guests:

```text
root-a <peer> root-b
  | active       | standby/recovery
  +------> child
              |
              +------> grandchild
```

It starts the packaged Arbor Registry OrbitDB/Helia transport daemon on every
guest, uses the packaged Python runtime to sign and reconcile a runtime
identity record, and exercises the real OpenBao HTTP →
`arbor-openbao-provider` → systemd-vaultd bridge on `child`. It checks
duplicate handling, quarantine, runtime secret delivery and rotation,
transport restart, a guest reboot, parent-service loss, a virtual firewall
partition, graph-risk planning, and real SSH connectivity.

Cross-peer OrbitDB replication is currently a bounded follow-up: the test
configures runtime peer bootstrap but does not claim replication until the
daemon exposes a passing cross-peer convergence assertion. It does prove the
real daemon and durable append/list path on every guest.

The test deliberately generates transport keys, registry socket tokens, SSH
keys, and the OpenBao value at VM runtime. No cluster identity or credential
is committed to the flake. The test only uses the NixOS test driver's private
network.

The passing run observed locally took about one minute after the Nix build
inputs were cached. Each guest is configured with 1536 MiB RAM and a 1 GiB
ephemeral test disk; four guests therefore need roughly 6 GiB of available
guest memory plus QEMU/Nix overhead.

Current non-VM boundaries are explicit. This target does not yet prove
cross-guest OrbitDB convergence, accepted peer/parent/recovery enrollment,
identity-generation recovery, unauthorized signed-record rejection, live
service/endpoint advertisement, or remote NixOS activation. The runtime has
no packaged long-running reconciliation service, so reconciliation is driven
by the packaged runtime from a VM-side scenario script. Arbor Manager's real
`deployment apply` path still requires an operator-supplied backend, and this
test does not claim remote `nixos-rebuild` activation or Colmena execution.
The existing component boundary tests remain authoritative for those adapter
contracts until these VM gaps are implemented.

During development, importing the published default registry NixOS module
alongside the vault runtime exposed a recursion/stack-overflow bug in its
recursive unsafe-value scan when it visits the derivation-valued
`runtimePackage`. The test intentionally avoids that unrelated policy module
while still exercising the packaged transport, runtime, OpenBao provider, and
upstream vaultd path. This is recorded as a component follow-up, not hidden
as a test assertion.
