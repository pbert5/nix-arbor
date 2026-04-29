# Bootstrap Scenarios

This guide collects the common bootstrap variants you are likely to use.

## Scenario: First Enrollment Over Raw IP

Use when:

- the host has no enrolled Ygg identity yet
- the host is only reachable over a raw management IP or a Tailscale address

Command shape:

```bash
nix run .#bootstrap-host -- \
  --host r640-0 \
  --target 100.64.0.10 \
  --identity-file /home/example/.ssh/bootstrap_key \
  --dry-run
```

Then enroll for real by dropping `--dry-run`.

## Scenario: Re-Read A Known Host Using Inventory Metadata

Use when:

- the host already has `targetHost` and `sshUser` in `inventory/host-bootstrap.nix`
- you want to avoid repeating the bootstrap target

Command shape:

```bash
nix run .#bootstrap-host -- \
  --host r640-0 \
  --identity-file /home/example/.ssh/bootstrap_key \
  --dry-run
```

## Scenario: Enroll And Promote Future Rollout To Ygg

Use when:

- the host has a valid Ygg identity
- you want deploy-rs and Colmena to prefer the enrolled Ygg address afterward

Command shape:

```bash
nix run .#bootstrap-host -- \
  --host r640-0 \
  --identity-file /home/example/.ssh/bootstrap_key \
  --deployment-transport privateYggdrasil
```

## Scenario: Enroll And Immediately Deploy

Use when:

- you trust the current transport path
- you want the first deployment right after enrollment

Command shape:

```bash
nix run .#bootstrap-host -- \
  --host r640-0 \
  --identity-file /home/example/.ssh/bootstrap_key \
  --deployment-transport privateYggdrasil \
  --deploy-tool deploy-rs
```

## Scenario: Enroll And Propagate Trust To Peers

Use when:

- the enrolled host is part of an explicit private Ygg peer graph
- peers need the updated trust data from inventory

Command shape:

```bash
nix run .#bootstrap-host -- \
  --host r640-0 \
  --identity-file /home/example/.ssh/bootstrap_key \
  --deployment-transport privateYggdrasil \
  --deploy-tool colmena \
  --deploy-peers
```
