# Private Overlay Network And Firewall

## Current Topology Model

The canonical topology data lives in
[`inventory/networks.nix`](/work/flake/inventory/networks.nix).

Tracked Ygg identity data now lives separately in
[`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
so the bootstrap workflow can update public metadata without rewriting the
whole topology file.

Operator-managed bootstrap and deployment metadata lives in
[`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix).
That file tracks bootstrap targets, SSH bootstrap users, operator-capable
markers, deployment tags, and whether rollout should currently prefer bootstrap
transport or private Ygg transport.

Network definitions live under nested layers:

- `public.intraLan`
- `public.interLan`
- `private.intraLan`
- `private.interLan`

Each enabled leaf can declare the dendrite that implements it. Normalization
publishes those leaves as named entries under `inventory.networks`.

Current network definitions:

- `tailscale`
  - dendrite: `network/tailscale`
  - layer: `private.interLan`
- `privateYggdrasil`
  - dendrite: `network/yggdrasil-private`
  - layer: `private.interLan`
  - `public = false` by default until fixed public-key identity is modeled in
    inventory
- `publicLanDhcp`, `publicYggdrasilPeering`, and `privateLanDhcp`
  - planned disabled leaves used to reserve the public/private and
    intra/inter-LAN shape

Current shared defaults:

- transport scheme: `tls`
- transport interface: `tailscale0`
- listener port: `14742`
- overlay interface name: `ygg0`
- `NodeInfoPrivacy = true`
- multicast disabled by default
- persistent keys enabled by default

Current site-wide firewall defaults:

- firewall enforcement enabled
- reverse-path filtering enabled (`checkReversePath = true`)
- listener port opening on the underlay enabled
- overlay TCP/UDP allowlists default to empty lists
- peer-source filtering defaults to off until all required peer identities are
  enrolled

## Host Network Selection

Hosts default to all enabled network leaves through
`org.network.membership.optIn = "all"`. A host can opt out of a named enabled
network with `org.network.membership.optOut`.

- `inventory/hosts.nix`
  - `r640-0`, `desktoptoodle`, and `t320-0` opt into `privateYggdrasil`
  - all active private Yggdrasil hosts also use Tailscale as the current
    underlay or bootstrap-access path
  - retired hosts such as `dev-machine` and the old placeholder
    `compute-worker` live under `inventory/deprecated/`

That means the current intent is:

- private Yggdrasil is an enabled private inter-LAN network across managed nodes
- Tailscale is the current underlay/bridge on exported machines
- public Yggdrasil peering is planned but disabled until the repo carries fixed
  identities and a clearer trust model

## Private Yggdrasil Dendrite

The implementation lives in
[`dendrites/network/dendrites/yggdrasil-private/yggdrasil-private.nix`](/work/flake/dendrites/network/dendrites/yggdrasil-private/yggdrasil-private.nix).

It currently does all of the following from inventory:

- enables Yggdrasil only on hosts with a matching node definition
- derives static peer URIs from the node peer graph
- supports transport schemes such as `tls`, `tcp`, `ws`, `wss`, or `quic`
- configures `IfName`, `Listen`, `Peers`, `NodeInfoPrivacy`, and related
  settings from site defaults plus per-node overrides
- supports optional `AllowedPublicKeys` allowlists derived from peer public keys
- appends `?key=<peer-public-key>` to peer URIs when a peer identity is enrolled
- can restrict all overlay input on `ygg0` to explicit peer source addresses
  when `firewall.overlay.restrictToPeerSources = true`
- optionally emits `networking.hosts` aliases for overlay addresses

### Overlay Alias Support

The module can generate pseudo-DNS entries like:

```nix
networking.hosts."200:1111:2222:3333::1" = [ "alpha-ygg" "alpha-overlay" ];
```

That support is implemented, and it now activates for whichever hosts have
addresses enrolled in
[`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix).
Hosts without enrolled addresses simply do not get an overlay alias yet.

## Firewall Model

The private overlay firewall model is intentionally stricter than just trusting
Yggdrasil peers.

Current behavior:

- enabling `network/yggdrasil-private` requires the host firewall to remain on
- the overlay interface (`ygg0` by default) gets explicit TCP/UDP allowlists
- the listener underlay interface (`tailscale0` by default) only opens the
  configured Yggdrasil listener port
- when `firewall.overlay.restrictToPeerSources = true`, the host injects an
  IPv6 source filter on `ygg0` so only explicit peer addresses can initiate
  overlay traffic
- `trustedInterfaces` is rejected for both:
  - the overlay interface
  - the Ygg listener underlay interface

This matters because a TUN-enabled Yggdrasil instance is routable IPv6 space,
so `AllowedPublicKeys` alone is not enough to protect services exposed over the
overlay.

### Current Default Policy

By default, overlay service exposure is deny-by-default.

To allow a service over the private overlay, define it explicitly under a host
or site firewall stanza, for example:

```nix
firewall.overlay.allowedTCPPorts = [ 18080 ];
```

That pattern is covered by the eval and smoke checks already shipped in the
flake.

### Peer Identity Lockdown

Strict overlay contact control needs more than port allowlists.

To fully lock a host down so only explicit peers can reach it over Ygg:

- enroll each peer's `address` and `publicKey`
- rebuild the enrolled hosts so `AllowedPublicKeys` and peer URI pinning take
  effect
- enable `firewall.overlay.restrictToPeerSources = true` for hosts that should
  reject all non-peer traffic on `ygg0`

That strict mode validates that every declared peer already has both identity
fields enrolled before evaluation succeeds.
