# Demo Inventory

This directory is a deliberately small example of the inventory style used by
the main flake.

It is not wired into the root flake automatically. The goal is to show the
shape of the data without dragging along the full homelab topology.

Files:

- `users.nix`
  - two example users
- `hosts.nix`
  - one workstation and one storage node
- `networks.nix`
  - a minimal private Yggdrasil overlay sketch
- `storage-fabric.nix`
  - a simplified storage-fabric example

Use it as a reference when adapting the pattern to your own machines.
