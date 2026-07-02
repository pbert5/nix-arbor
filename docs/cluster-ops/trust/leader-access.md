# Leader Access

Leader machines are trusted deployer nodes. Inventory users marked as leader
users receive a host-specific key that can SSH as `root` to every managed host,
including other leaders.

## Current Leaders

- `desktoptoodle`
- `r640-0`

## Current Leader User

`user1` is marked with:

```nix
org.clusterIdentity.role = "leader";
```

in `inventory/users.nix`.

## Where The Keys Live

- Public records:
  `inventory/identity-services/leader-user-ssh.nix`
- Private keys:
  `inventory/keys/identities/cluster-private-identities.sops.yaml`
- Installed leader path:
  `/home/example/.ssh/cluster-leader-ed25519`

Each leader host has its own key. The private key is installed only for the
declared leader user on that leader.

On leader hosts, that user also joins the `cluster-identity` and `ipfs` groups.
The leader working registry and anti-rollback state are owned by the leader
user, while the host age key remains root-owned and group-readable. This lets
normal registry inspection, publication, key generation, IPFS fetch, and
deployment run from the leader account without elevating the whole command.
Root remains responsible for activation, SOPS installation, and the IPNS
private-key import service.

## How They Get Applied

The base SSH leaf reads every enrolled `leader-user-ssh` public record and
merges those keys into:

```nix
users.users.root.openssh.authorizedKeys.keys
```

That same shared leaf also disables SSH password and keyboard-interactive
authentication fleet-wide, so root access is key-only.

Implementation:

- [`dendrites/base/leaves/services.nix`](/work/flake/dendrites/base/leaves/services.nix)

The legacy public files under `inventory/keys/leaders/` remain trusted during
migration and emergency recovery.

That means:

- every host trusts every leader deployer key for root SSH
- leaders can deploy to ordinary nodes
- leaders can also deploy to each other

## Enrollment

```bash
clusterctl identity generate-missing --service leader-user-ssh --dry-run
clusterctl identity generate-missing --service leader-user-ssh --no-publish
clusterctl deploy all
```

The identity solver requires this service only for hosts whose cluster identity
role is `leader`. Generation derives the leader user from user inventory,
creates the public and encrypted private records, and stages those ledger
changes for flake evaluation.

## When To Add A New Leader

Mark a user as a leader user when that account should be able to run
cluster-wide rollouts from leader machines.

The minimum steps are:

1. set `org.clusterIdentity.role = "leader"` on the user
2. ensure the user is selected by each leader host
3. run the `leader-user-ssh` generator
4. rebuild the fleet so every host receives the new root authorized key

## Relationship To Host Bootstrap

Leader root access is a trust/distribution mechanism.

Bootstrap metadata in
[`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
is a transport/rollout mechanism.

They are related, but not the same thing:

- leader keys answer "who may deploy as root"
- bootstrap metadata answers "how do we reach this host right now"
