# Bootstrap Validation

Run validation before you bootstrap a host, switch a host to Ygg transport, or
start a fleet rollout from a leader.

## Commands

```bash
nix run .#bootstrap-validate
nix run .#nbootstrap -- validate
nix run .#bootstrap-validate -- --json
```

## What It Checks

- every exported host has bootstrap metadata
- every generated `deploy-rs` node exists and resolves to a hostname
- `privateYggdrasil` deployment targets are enrolled and still use the logical
  host name for SSH resolution
- operator-capable hosts have a matching
  `inventory/keys/leaders/<host>-root-deployer.txt`
- leader key files point at real operator-capable hosts
- bootstrap `identityFile` paths do not use date-stamped filenames
- locally referenced `identityFile` paths exist on the machine running the
  validator

## When To Treat Warnings As Real Problems

Warnings are local-machine checks. The most common one is "the private key path
does not exist on this machine."

That is fine on a follower that is not supposed to deploy a given target.
It is not fine on a leader you expect to run `deploy-rs` or `bootstrap-host`
from.

## Suggested Workflow

1. run `nix run .#bootstrap-validate`
2. fix any inventory or leader-key errors first
3. test raw SSH reachability
4. run `nix run .#nbootstrap -- host bootstrap ... --dry-run`
5. enroll or redeploy only after the validator is clean
