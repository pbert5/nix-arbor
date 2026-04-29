# Trust Rollout

Enrolling a host identity does not instantly make every other node trust it.

The trust graph is inventory-driven, so other hosts only learn about the new
public key after they receive updated configuration.

## Normal Sequence

1. enroll or refresh the host identity
2. rebuild the enrolled host
3. rebuild peers that should trust that identity
4. only then enable stricter peer-only contact controls if desired

## Why This Matters

These are separate layers:

- peer URI pinning
- `AllowedPublicKeys`
- overlay service firewall policy
- optional peer-source filtering on `ygg0`

If only one side has the new config, the mesh may still partially work but not
fully reflect the intended trust posture.

## When To Enable Strict Peer-Only Contact

Enable `firewall.overlay.restrictToPeerSources = true` only after:

- every peer listed in the host's Ygg node data has an enrolled `address`
- every peer listed in the host's Ygg node data has an enrolled `publicKey`
- the relevant peers have been redeployed
