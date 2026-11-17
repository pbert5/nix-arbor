# Arbor tools

Run these executables from any working directory via their checkout paths. They
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
