# `network/yggdrasil-public-peering`

Public inter-LAN Yggdrasil peering sidecar.

This dendrite runs a second Yggdrasil process with `IfName = "none"`. It is
for peering and bridge reachability only; it does not create a routable host
interface and does not expose service ports on a Yggdrasil address.

The private `network/yggdrasil-private` layer remains the regulated service
overlay.
