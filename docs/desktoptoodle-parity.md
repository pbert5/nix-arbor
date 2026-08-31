# desktoptoodle live parity evidence

Verified 2026-08-31 from the live host `desktoptoodle` over its existing
bootstrap SSH path. This is an evidence record for the host-parity gate; it
does not authorize activation.

## Result

**DESKTOPTOODLE PARITY: PASS**

The checked-in hardware and access-critical model matches the live machine.
The live system is on an older NixOS generation than the current exact
toplevel build; this is a planned staged upgrade (`SAFE DIFFERENCE`), not a
hardware or access mismatch.

## Compared facts

| Fact | Live evidence | Repository model | Classification |
| --- | --- | --- | --- |
| Hostname | `desktoptoodle` | `networking.hostName = "desktoptoodle"` | PASS |
| Boot | EFI; `/boot` vfat UUID `50CC-DE00` | same UUID and systemd-boot | PASS |
| Root | ext4 UUID `34b704be-0c38-4663-8eb2-fa24e2a2b578` | same UUID | PASS |
| Home | ext4 UUID `bb7ff4a0-8b82-41ab-a680-2cf41549ceb7` | same UUID | PASS |
| Swap | UUID `67d7662f-1a5f-47e9-8eef-f47a50caf60b` | same UUID | PASS |
| Primary wired NIC | `eno1` present and up | NetworkManager enabled; no fixed NIC identity required | PASS |
| SSH | root login prohibited-password; password and keyboard-interactive auth disabled | same settings | PASS |
| Desktop | `greetd` running; NVIDIA kernel modules loaded | desktop profile and NVIDIA/desktop inputs | PASS |
| Workstation services | Docker and public Ygg sidecar running | desktop configuration retains Docker and public-Ygg policy | PASS |
| NixOS generation | `26.05.20260630.95ca1e2` | exact current flake toplevel builds as `26.11.20260822.2c423e0` | SAFE DIFFERENCE |
| Arbor trust | no accepted physical graph was used for this comparison | intentionally runtime-owned | GATED |

The existing live Yggdrasil service is legacy public transport. It is not
used as evidence of Arbor trust or private-Ygg enrollment.

## Reproduction

The live observations were collected with read-only commands equivalent to:

```sh
nixos-version
findmnt -o TARGET,SOURCE,FSTYPE,OPTIONS
swapon --show
ip -br link
lsblk -o NAME,FSTYPE,LABEL,UUID,MOUNTPOINTS
sshd -T
systemctl is-active greetd docker yggdrasil-public-peering
```

The exact current toplevel was built with:

```sh
nix build --no-link .#nixosConfigurations.desktoptoodle.config.system.build.toplevel
```

The resulting path was
`/nix/store/j1n6jhi126fkiwp3dxm550v8hn398rqx-nixos-system-desktoptoodle-26.11.20260822.2c423e0`.

This evidence is sufficient to remove the historical parity-branch-name
dependency. Activation remains separately gated on deployment privilege,
Registry bootstrap, and accepted private-Ygg state.
