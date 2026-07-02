# Direct Ethernet link

`network/direct-link` configures a private, gateway-free Ethernet connection
between two hosts. Each endpoint declares its interface, local CIDR, peer name,
and peer address under `org.network.directLink`.

The current link is:

| Host | Interface | Address |
| --- | --- | --- |
| `desktoptoodle` | `eno1` | `10.200.0.1/30` |
| `t320-0` | `eno2` | `10.200.0.2/30` |

NetworkManager receives a static profile with no default route, so ordinary
internet access continues to use each host's existing LAN connection. The
dendrite also adds an SSH alias named `<peer>-direct`; from `desktoptoodle`, use
`ssh t320-0-direct` for the gigabit path.
