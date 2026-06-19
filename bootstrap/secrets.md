# Bootstrap Secrets

The repo now carries an `agenix` foundation for encrypted secret delivery.

That gives us a Nix-native path for:

- encrypted bootstrap credentials committed to the repo
- per-host secret decryption during activation
- leader-only access to shared operator/bootstrap secrets
- narrower host-level access for followers and workers

## Why `agenix`

`agenix` matches the repo's existing trust model well:

- public recipient keys can be committed
- private decryption keys stay on the machine that owns them
- NixOS activation decrypts secrets locally on the target
- the repo can safely carry encrypted blobs without leaking plaintext into the
  Nix store

The upstream project describes it as SSH-key-based `age` secret management for
NixOS and Home Manager. Source:
https://github.com/ryantm/agenix

## Recipient Model

Use three tiers of recipients:

1. leaders
   shared operator/bootstrap secrets encrypted to leader deployer public keys
2. host-specific
   secrets encrypted to the target host's SSH host key so only that machine can
   decrypt them at activation time
3. mixed service groups
   secrets encrypted to a small set of leaders plus the exact hosts that need
   runtime access

## What Should Move Into Encrypted Secrets

- bootstrap-only credentials that are currently passed around manually
- service passwords, API tokens, and recovery material
- any future cluster-wide credentials that should be readable by leaders but
  not ordinary followers

Keep these out of encrypted repo secrets:

- transient machine-local state that should be generated on first boot
- large private datasets
- private keys that should never leave the originating machine

## Next Inventory Work To Finish The Migration

Before host-specific secrets can be encrypted cleanly, we should record stable
recipient public keys for each managed host, ideally the SSH host public keys
used for decryption on that host.

Until then, the safe immediate use case is leader-readable bootstrap/operator
secrets encrypted to the public keys already tracked under
[`inventory/keys/leaders/`](/work/flake/inventory/keys/leaders).
