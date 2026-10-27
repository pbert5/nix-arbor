# Private-Ygg participant enrollment

The `privateYggParticipant` profile composes the pinned
`yggdrasil-private` module in its Arbor Network Manager mode on `r640-0`,
`desktoptoodle`, and `eVolver`.  It supplies the Arbor Network Manager
package and `/run/arbor/ygg-provider.sock`; the external module remains the
owner of Yggdrasil transport, persistent keys, `AllowedPublicKeys`, firewall
separation, and bootstrap/public fallback behavior.

This checkout does not currently contain authoritative private-Ygg node
records for those hosts.  Enrollment must therefore provide, through the
normal accepted Arbor inventory/runtime boundary, a
`site.networks.privateYggdrasil.nodes.<host>` record containing the host's
public address and public key, plus the accepted peer relationships.  Private
Ygg keys must remain runtime secret material.  Until those records exist, the
profile is intentionally dormant: it does not invent identities, addresses,
or static peers.

The provider socket is the runtime peer authority when the node is enrolled;
Yggdrasil discovery remains transport-only and never grants Arbor trust.
