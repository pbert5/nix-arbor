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
guest and exercises the real OpenBao HTTP →
`arbor-openbao-provider` → systemd-vaultd bridge on `child`. It checks
duplicate handling, quarantine, runtime secret delivery and rotation,
transport restart, a guest reboot, parent-service loss, a virtual firewall
partition, graph-risk planning, and real SSH connectivity.

All guests receive the same public per-test transport realm ID and protocol
epoch. Each independently derives the same OrbitDB registry address; the test
then performs bounded raw replication in both directions (`root-a` to `child`
and `child` to `root-b`) and appends from multiple guests. This proves network,
libp2p, OrbitDB, and raw transport convergence. Accepted/materialized Arbor
reconciliation remains a separate follow-up gate.

The duplicate/quarantine assertions currently run against the packaged local
reconciliation runtime on one guest; they are not cross-guest accepted-state
assertions. The firewall section likewise proves only the VM harness can block
and heal a route. The test deliberately generates transport keys, registry socket tokens, SSH
keys, and the OpenBao value at VM runtime. No cluster identity or credential
is committed to the flake. The test only uses the NixOS test driver's private
network.

The passing run observed locally took 36.94 seconds after the Nix build
inputs were cached. Each guest is configured with 1536 MiB RAM and a 1 GiB
ephemeral test disk; four guests therefore need roughly 6 GiB of available
guest memory plus QEMU/Nix overhead.

Current non-VM boundaries are explicit. This target does not yet prove
cross-guest accepted peer/parent/recovery enrollment,
identity-generation recovery, unauthorized signed-record rejection, live
service/endpoint advertisement, or remote NixOS activation. The runtime has
no packaged long-running reconciliation service, so reconciliation is driven
by the packaged runtime from a VM-side scenario script. Arbor Manager's real
`deployment apply` path still requires an operator-supplied backend, and this
test does not claim remote `nixos-rebuild` activation or Colmena execution.
The existing component boundary tests remain authoritative for those adapter
contracts until these VM gaps are implemented.

The published Arbor Registry vault runtime module is used through its normal
`vault-runtime-upstream` export. Its derivation-valued `runtimePackage` scan
was fixed in arbor-registry `823e02e`, and the transport realm/bootstrap fix
was promoted as `16029ce`, with focused component regressions; the lock file
pins the latter promoted revision.
