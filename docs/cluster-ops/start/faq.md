# Cluster Ops FAQ

## Why Do We Have Both `bootstrap-host` And `yggdrasil-bootstrap`?

They currently point at the same tool, but they communicate different intent.

- `yggdrasil-bootstrap` names the mechanism
- `bootstrap-host` names the operator workflow

Use `bootstrap-host` in normal operator docs and muscle memory.

## Why Does `bootstrap-host --dry-run` Matter?

It proves the leader can reach the host, ensures the Ygg identity exists, and
shows exactly what public metadata would be written back into inventory without
changing the repo.

## Why Not Store Private Ygg Keys In The Repo?

Because the current trust model prefers host-generated private keys and
repo-recorded public metadata. That keeps stable identity without turning the
repo into a distribution channel for every host's Ygg secret.

## Why Did `deploy-rs` Start Using A `202:...` Address?

Because the generated deploy surface switched from bootstrap transport to the
host's enrolled private Ygg address.

## Why Can A Host Still Answer Ping Even If Services Are Locked Down?

Because service-port filtering, peering identity restrictions, and general
ICMP/firewall behavior are related but separate layers.

## Why Do Other Hosts Need Redeploy After Enrollment?

Because peer trust is configuration-driven. They only learn the new public key
after receiving updated evaluated config from the repo.

## Should Every Machine Be A Leader?

No. Only machines that should act as cluster control points should have leader
deployer keys distributed fleet-wide.
