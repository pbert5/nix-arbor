# `network/warpinator`

LAN file transfer for interactive hosts.

## Main Effects

- installs `warpinator` system-wide
- opens TCP 42000 for transfers and TCP 42001 for authentication
- opens UDP 42000 for compatibility with Warpinator clients older than 1.2.0

This dendrite does not open UDP 5353 because it is only required when
connecting Flatpak Warpinator clients; this dendrite installs the native Nix
package. Other selected services may still open that port independently.

## Requirements

- requires `network`
- intended for explicitly selected interactive hosts
