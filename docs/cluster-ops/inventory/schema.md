# Inventory Schema Reference

This page is the field-level reference for the cluster-ops inventory surfaces.

## `inventory/host-bootstrap.nix`

Per-host operator-side transport metadata.

### `targetHost`

Bootstrap endpoint for reaching the host before or during normal deployment.

Typical values:

- raw management IPv4 address
- Tailscale IPv4 address
- DNS name if you have one

### `sshUser`

The SSH login user for bootstrap and deployment. In the current cluster model
this is normally `root`.

### `identityFile`

Optional local private key path to pass to generated deploy-rs SSH options for
that target.

The repo stores the path only. The private key must exist on the operator
machine running deploy-rs.

Prefer a stable alias such as `/home/example/.ssh/deploy_rsa` instead of a
date-stamped filename so the deployment surface stays portable across machine
transfers and key rotations.

### `deploymentTransport`

Which generated transport should be preferred for normal deployment.

Current values in use:

- `bootstrap`
- `privateYggdrasil`

### `deploymentTags`

Free-form operator tagging for deployment grouping or future rollout logic.

### `operatorCapable`

Marks a host as a leader-capable operator machine.

Operationally this means:

- it is expected to be a cluster control point
- its deployer key should exist under `inventory/keys/leaders/`

## `inventory/guest-access.nix`

Declarative non-leader access policy.

Selectors use these forms:

- `"all"` selects every available target
- `"none"` selects no targets
- `[ "name-a" "name-b" ]` selects explicit targets

### `guests`

Named external identities. A guest may carry SSH keys, Yggdrasil identity
material, or both.

```nix
guests.friend = {
  ssh.authorizedKeys = [
    "ssh-ed25519 AAAA... friend@example"
  ];

  yggdrasil = {
    address = "200:...";
    publicKey = "...";
    aliases = [ "friend-ygg" ];
  };
};
```

### `ssh.grants`

Named SSH grants. A grant resolves keys from `guests`, inline `keys`, or both.
It then scopes those keys to target hosts and target users.

```nix
ssh.grants.friend-shell = {
  guests = [ "friend" ];
  hosts = [ "r640-0" "t320-0" ];
  users = [ "user1" ];
};
```

Target users must already be active on the target host. The special user
`root` must be requested explicitly; `users = "all"` expands to the normal
inventory users enabled on each target host.

### `yggdrasil.trustedGuests`

Named private-Yggdrasil trust grants. Each grant resolves a Yggdrasil public
key from the matching `guests.<name>.yggdrasil.publicKey` entry unless the
grant provides `publicKey` inline.

```nix
yggdrasil.trustedGuests.friend = {
  hosts = "all";
};
```

The private Yggdrasil module appends these public keys to the target host's
`AllowedPublicKeys`. If a target host enables peer-source firewall filtering,
the grant must also resolve an `address`.

## `inventory/private-yggdrasil-identities.nix`

Per-host public Ygg identity metadata.

### `address`

The host's expected Ygg IPv6 address derived from its public identity.

### `publicKey`

The host's Ygg public key used for peer identity pinning and allowlists.

## `inventory/hosts.nix`

This remains the durable host-composition surface.

The bootstrap tool should not use it as a scratchpad for transport state.

Relevant fields for cluster ops include:

- `dendrites`
- `facts`
- `org.*`

## `inventory/users.nix`

Normal user identity and login policy.

### `nixos.shellPackage`

Nixpkgs package attribute used as the user's login shell. The corresponding
NixOS program module must also be enabled so the shell is registered in
`/etc/shells`; the shared base dendrite currently does this for `zsh`.

### `nixos.authorizedKeysFile`

Path to a paste-friendly SSH public key file for that user. Each file contains
one public key per line. Blank lines and lines starting with `#` are ignored.

Current user key files:

- `inventory/keys/user1-authorized-keys.txt`
- `inventory/keys/user2-authorized-keys.txt`

### `nixos.authorizedKeysFiles`

Optional list of additional key files to merge into the same user.

### `nixos.authorizedKeys`

Optional inline list of SSH public keys. Prefer a key file when you expect to
copy/paste or rotate keys by hand.

Network membership is declared under `org.network.membership` and normalized
to the generated `networks` field.

### `org.nix.distributedBuilds`

Host-local coordinator settings for the `system/distributed-builds` dendrite.

Important fields:

- `builders`
  inventory host names to use as remote build machines
- `sshKey`
  local private key path used by the coordinator's Nix daemon
- `buildersUseSubstitutes`
  optional override for `nix.settings.builders-use-substitutes`

### `org.nix.buildMachine`

Host-local scheduler hints used when another machine lists this host as a
builder.

Important fields:

- `maxJobs`
- `speedFactor`
- `systems`
- `supportedFeatures`
- `mandatoryFeatures`
- `publicHostKey`

## `inventory/networks.nix`

This is where topology and policy live.

Relevant cluster-op concerns include:

- overlay listener endpoints
- peer graph
- firewall defaults
- per-node overlay policy

## `inventory/keys/leaders/`

Each regular file in this directory is treated as a trusted leader deployer key
source for root SSH access across the fleet.
