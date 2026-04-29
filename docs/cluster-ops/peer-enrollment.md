# Peer Enrollment

This guide focuses on the trust meaning of enrollment rather than just the
mechanics of running the bootstrap command.

## What Enrollment Actually Publishes

When a host is enrolled, the repo records public metadata:

- host name
- Ygg public key
- derived Ygg IPv6 address
- operator-side bootstrap and deployment metadata

This does not publish:

- the host's private Ygg key
- arbitrary host secrets

## Why The Public Key Matters

The private Ygg mesh uses the enrolled public key in two important ways:

- pinning peer URIs so outbound peering targets are identity-bound
- populating `AllowedPublicKeys` so inbound peering can be restricted

That means enrollment is not just informational; it is the basis of actual mesh
trust.

## The Enrollment Sequence

1. ensure root SSH reachability from a trusted leader
2. run `bootstrap-host --dry-run` to confirm the discovered identity
3. run the real bootstrap command to write identity metadata into inventory
4. deploy the enrolled host
5. deploy any peers that should now trust the new identity

## Why Existing Peers Still Need Deployment

Existing peers do not learn about the new public key by magic.

They only learn it when their generated configuration is reevaluated and
deployed.

Until then, you may see a mix of:

- partial connectivity
- current service reachability but missing strict pinning
- old trust posture still active on some nodes

## Good Operational Rule

Treat bootstrap enrollment as "the host now has a recorded public identity",
not "the whole fleet has already accepted it".
