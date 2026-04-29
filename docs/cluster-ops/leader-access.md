# Leader Access

Leader machines are trusted deployer nodes that should be able to SSH as
`root` to every managed host, including each other.

## Current Leaders

- `desktoptoodle`
- `r640-0`

## Where The Trusted Keys Live

All leader deployer public keys live under:

```text
inventory/keys/leaders/
```

Current files:

- [`desktoptoodle-root-deployer.txt`](/work/flake/inventory/keys/leaders/desktoptoodle-root-deployer.txt)
- [`r640-0-root-deployer.txt`](/work/flake/inventory/keys/leaders/r640-0-root-deployer.txt)

## How They Get Applied

The base SSH leaf loads every regular file in `inventory/keys/leaders/` and
merges those keys into:

```nix
users.users.root.openssh.authorizedKeys.keys
```

Implementation:

- [`dendrites/base/leaves/services.nix`](/work/flake/dendrites/base/leaves/services.nix)

That means:

- every host trusts every leader deployer key for root SSH
- leaders can deploy to ordinary nodes
- leaders can also deploy to each other

## Private Key Requirement

The repo only distributes leader public keys.

Each leader machine must also have its own matching private deploy key locally.
Without that private key, the fleet may trust the leader's public key but the
leader still cannot initiate SSH to anyone.

Recommended model:

- generate the leader's private deploy key on that leader
- keep the private key on that machine
- commit only the matching public key under `inventory/keys/leaders/`

This is the same trust shape we want for Ygg identities: host-generated private
material and centrally recorded public metadata.

## Current `r640-0` Note

`r640-0` now uses a host-generated root deploy key at `/root/.ssh/id_ed25519`.
The committed public key in
[`inventory/keys/leaders/r640-0-root-deployer.txt`](/work/flake/inventory/keys/leaders/r640-0-root-deployer.txt:1)
must be deployed to peers before `r640-0` can root-SSH into them with that key.

## When To Add A New Leader

Add a leader deployer key when a machine should be able to run cluster-wide
rollouts.

The minimum steps are:

1. add its public deployer key file under `inventory/keys/leaders/`
2. mark the host as operator-capable in
   [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
3. rebuild the fleet so every host receives the new root authorized key

## Relationship To Host Bootstrap

Leader root access is a trust/distribution mechanism.

Bootstrap metadata in
[`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
is a transport/rollout mechanism.

They are related, but not the same thing:

- leader keys answer "who may deploy as root"
- bootstrap metadata answers "how do we reach this host right now"
