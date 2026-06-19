# Cluster Ops Glossary

## Bootstrap Transport

The raw path used to reach a machine before normal Ygg-based operations are in
place, usually an IP address or Tailscale endpoint.

## Deployment Transport

The transport the generated deployment surface should prefer for normal
operations.

## Trusted Leader

A machine whose deployer public key is distributed to every host for root SSH
access and which is allowed to act as a cluster control point.

## Enrolled Identity

The recorded public Ygg metadata for a host: its public key and expected Ygg
address.

## Private Ygg

The repo-managed private Yggdrasil overlay defined by topology and public peer
metadata in inventory.

## Trust Rollout

The follow-up deployment needed so other nodes actually receive and apply new
public identity data after a host is enrolled.

## Peer URI Pinning

Including the expected peer public key in the generated Ygg peering URI so the
remote identity is bound, not just the network location.

## Strict Peer-Only Contact

The tighter posture where only explicitly defined peers should be able to have
meaningful contact over the private Ygg overlay, reached only after the needed
peer metadata exists and has been deployed.
