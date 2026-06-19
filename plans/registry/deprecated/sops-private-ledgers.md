# SOPS Private Ledgers

## Purpose

Private identity material belongs in the flake, but not in plaintext Git.
`sops-nix` is the declarative secret substrate for this part of the registry
plan.

The design separates two concerns:

- host base age keys used to decrypt host-targeted material
- service identities such as Yggdrasil, Radicle, SSH, and git-annex keys

That separation lets a host age key rotate without forcing every service
identity to rotate.

## Files

SOPS policy:

```text
.sops.yaml
```

Private service identity ledger:

```text
inventory/keys/identities/cluster-private-identities.sops.yaml
```

Host age private key recovery ledger:

```text
inventory/keys/followers/host-age-private-keys.sops.yaml
```

Public host age recipient inventory:

```text
inventory/keys/host-age-recipients.nix
```

Public identity source ledger:

```text
inventory/identities.nix
```

## Creation Policy

`.sops.yaml` encrypts identity and follower ledgers to leader host age
recipients:

```text
r640-0
desktoptoodle
```

The current recipient strings come from enrolled leader entries in
`inventory/keys/host-age-recipients.nix`.

## Nix Integration

The root flake includes:

```nix
sops-nix.url = "github:Mic92/sops-nix";
```

Host assembly imports:

```nix
inputs.sops-nix.nixosModules.sops
```

The `system/cluster-identity` dendrite configures:

```text
SOPS_AGE_KEY_FILE=/var/lib/cluster-identity/age/host.agekey
sops.age.keyFile=/var/lib/cluster-identity/age/host.agekey
sops.defaultSopsFile=inventory/keys/identities/cluster-private-identities.sops.yaml
```

It also creates:

```text
/var/lib/cluster-identity/age
```

## Host Age Key Bootstrap

The only accepted bootstrap exception is installing a host's base age private
key at:

```text
/var/lib/cluster-identity/age/host.agekey
```

This key can be installed over root SSH during enrollment. That bootstrap path
must not install service identities directly.

Planned command shape:

```bash
clusterctl host-age bootstrap HOST
```

Expected behavior:

- read the target host key from the leader-encrypted follower SOPS ledger
- SSH to the target through the best available bootstrap path
- create `/var/lib/cluster-identity/age`
- install `host.agekey` as root-owned secret material
- record or verify the public recipient in `inventory/keys/host-age-recipients.nix`

## Private Service Identities

Private service identity material should be stored in:

```text
inventory/keys/identities/cluster-private-identities.sops.yaml
```

Public facts and delivery metadata should be stored in:

```text
inventory/identities.nix
```

For example, a public Yggdrasil record in `inventory/identities.nix` can point
at a private delivery target:

```nix
private = {
  status = "not-yet-imported-to-encrypted-ledger";
  recipientHost = "r640-0";
  targetPath = "/var/lib/yggdrasil/private.key";
};
```

`clusterctl identity publish` mirrors that block into registry
`privateDelivery` metadata. It does not copy the private key into the registry.

## Delivery Model

MVP delivery can still use root SSH:

```bash
clusterctl bundle publish r640-0 yggdrasil \
  --generation 2 \
  --source /tmp/r640-0-yggdrasil-private.key \
  --target-path /var/lib/yggdrasil/private.key
```

Planned delivery should instead:

- read private service material from the SOPS ledger
- encrypt a host-targeted bundle to the target host age recipient
- publish only bundle metadata or encrypted bundle material to the registry
- require target receipts before active promotion when policy requires it

## Rotation Model

Host age key rotation:

1. Generate a new host age keypair.
2. Update the follower SOPS recovery ledger.
3. Update `inventory/keys/host-age-recipients.nix`.
4. Publish the flake identity ledger to the registry.
5. Bootstrap the new host age private key to the target.
6. Re-encrypt future private bundles to the new recipient.

Service identity rotation:

1. Generate a new service keypair.
2. Store private material in the private SOPS identity ledger.
3. Update public facts and timestamps in `inventory/identities.nix`.
4. Publish the flake identity ledger.
5. Deliver host-targeted private material.
6. Collect receipt and promote when appropriate.

## Important Constraint

If a recipient sees a newer registry event it cannot decrypt, it should prefer
the newest decryptable event for its own runtime state until the intended host
age key is installed. This keeps a stale but usable identity from being
needlessly annulled by an unreachable encrypted delivery.
