# Strict Lockdown

This guide describes the stricter posture you asked for: only explicitly
defined peers should have any contact over the private Ygg overlay.

## What "Strict" Means Here

There are several layers and they are not identical:

- peer URI pinning
- `AllowedPublicKeys`
- overlay service-port filtering
- peer-source filtering on `ygg0`

The final posture only exists when the host has enough metadata to enable all
of the layers it needs.

## Current Implementation Surfaces

The private Ygg dendrite already supports:

- peer URI key pinning
- `AllowedPublicKeys`
- optional `firewall.overlay.restrictToPeerSources = true`

Implementation:

- [`dendrites/network/dendrites/yggdrasil-private/yggdrasil-private.nix`](/work/flake/dendrites/network/dendrites/yggdrasil-private/yggdrasil-private.nix)

## Preconditions

Do not enable strict peer-source filtering until:

- every declared peer has an enrolled `publicKey`
- every declared peer has an enrolled `address`
- the relevant hosts have been redeployed

If you skip those prerequisites, you risk creating asymmetric mesh behavior or
breaking wanted traffic.

## Recommended Enablement Sequence

1. enroll the host
2. enroll its declared peers
3. deploy the host and peers with the new public identities
4. verify deploy targets and peering inputs
5. then enable `firewall.overlay.restrictToPeerSources = true`
6. redeploy the affected hosts

## Important Reality Check

Locking down service ports is not the same thing as blocking all overlay
contact.

For example:

- a host may still respond to ICMPv6 if the general firewall policy allows it
- `AllowedPublicKeys` controls peering identity, not every possible upper-layer
  packet on `ygg0`

That is why this repo models strictness as a staged posture, not a single
switch flipped on day one.
