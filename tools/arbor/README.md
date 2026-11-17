# Arbor tools

Run the Manager snapshot and network executables from any working directory via their checkout paths. They
use the root flake's locked Arbor Manager package; Nix with flakes enabled and
cached or fetchable flake inputs are required. Component submodules and a
separate Arbor CLI installation are not required.

```sh
tools/arbor/status --snapshot deployment.json --socket /run/arbor/networkd.sock
tools/arbor/nodes --snapshot deployment.json --scope selected --format names
tools/arbor/inspect --snapshot deployment.json --name my-node
tools/arbor/snapshot --snapshot deployment.json
tools/arbor/plan --snapshot deployment.json --format text
tools/arbor/network status --socket /run/arbor/networkd.sock
```

Use `--help` on any command for options. Snapshot, nodes, inspect and plan
read an existing Manager deployment snapshot and use Manager's validation;
they do not generate a Registry snapshot. Snapshot prints the validated
snapshot, while plan presents its embedded deployment plan. Network queries
require an explicit socket. Status exits nonzero if either input was omitted,
invalid, or unavailable, and reports each separately. A reachable network daemon
may still report `ready: false` or a reload error; inspect its returned status. Snapshot output includes the raw snapshot; plan output is also unredacted. Both
can contain sensitive fields;
handle it accordingly. These commands do not deploy or modify hosts.

## Local Registry

From the r640 checkout, check each host separately. These commands use Bash,
jq, systemd, sudo and the Manager adapter from the running Registry service's
Nix store package. A build or a checkout on eVolver is unnecessary. The
r640-0 target runs locally and checks the hostname. The eVolver target uses
the configured `root-evolver` SSH alias with strict host-key checking, public
key authentication and no remote terminal. In VS Code, choose **Tasks: Run Task** and select **Arbor: Registry**.
Run local identity commands in a
terminal if sudo needs your password. Only the adapter runs as `arbor-registry`;
it reads the token itself.

```sh
tools/arbor/registry status r640-0
tools/arbor/registry status eVolver
tools/arbor/registry inspect r640-0
tools/arbor/registry inspect eVolver
tools/arbor/registry summary r640-0
tools/arbor/registry summary eVolver
```

Status checks both unit states, their canary state directories, the local IPC
configuration and the masked status probe. Inspect discovers any existing
local identity. Summary also checks public record and projection counts.
A fresh host has `initialized: false`, no discovered node and zero records.
If a check fails, stop and inspect that host's unit status and configuration.
Retain historical state and any unclaimed key material.

When ready to initialize an independent root on each host, run the following
one at a time. Each invocation writes genesis for the selected host in
`nix-arbor-live-v1` or asks the daemon to verify an existing matching genesis.
The daemon rejects conflicting domains and keys. A failed initialization may
have written state. Inspect and summarize the host before any retry.

```sh
tools/arbor/registry init-self r640-0
tools/arbor/registry init-self eVolver
```

Record the public fingerprint from each result and verify the two differ.
Expect generation 1, local genesis, self-rooted, zero parents and zero peers.
The two identities have independent authority. Peering, enrollment and private
Ygg activation are outside this workflow.

To test persistence during a maintenance window, restart one Registry daemon
at a time. The command requires an initialized identity, keeps the transport
running, waits for the adapter and compares the full public identity against
the pre-restart inspection. A mismatch or unavailable service exits nonzero.

```sh
tools/arbor/registry restart-check r640-0
tools/arbor/registry restart-check eVolver
```

For checkout setup and machine switch commands, see the
[checkout tools guide](../README.md). The [synthetic acceptance harness](../../tests/arbor-registry/README.md)
runs separately from either host.
