# r640-0 cutover readiness

This configuration is intended to replace the reduced Flake Devbox scope on
the physical host. It does not enable Arbor Registry, Annex, SeaweedFS,
Radicle, Matrix, distributed builds, or an operational Yggdrasil dependency.

## Proven by evaluation/build checks

- x86_64 Linux, hostname `r640-0`, systemd-boot, ext4 `/`, VFAT `/boot`.
- LVM discovery remains disabled.
- `networking.hostId = "cbda65de"`; ZFS support imports existing pool
  `mypool` without a create/format/destroy operation or forced import.
- `ash` (verified UID 1000, primary GID 100), `madeline` (UID 1001),
  `wheel`, and `home-share` (GID 993) are declared. Ash has the three
  existing migration keys plus six additional public keys recovered exactly
  from the trusted legacy access ledger. The live-only `ash@k8head0` key
  material was not recoverable and is not fabricated; root SSH is key-only
  and has no configured key.
- NetworkManager is enabled with DHCP on `eno3` and `eno4`.
- Docker is available to the declared users (including the `docker` group),
  but no workloads are deployed by this configuration.
- Home Manager, AshZsh, server tooling, Git identity, and safe home-share
  link services are composed for r640.
- SOPS/age is wired but disabled until the operator provisions the encrypted
  file and host age key outside Git.

## Physical preflight (read-only)

Run locally or through an already-working recovery path before switching:

```sh
bootctl status
ip -brief address
tailscale status
ssh -o BatchMode=yes ash@<lan-address> true
sudo zpool status -x mypool
sudo zpool list mypool
sudo zfs list -o name,mountpoint,canmount,mounted
sudo zfs get -r mountpoint mypool
df -h / /boot /mypool
getent passwd ash
id ash
stat -c '%u:%g %a %n' /home/ash /home/madeline
test "$(hostid)" = cbda65de
nmcli device show eno3 eno4
systemctl is-active NetworkManager
docker info
docker ps --all
```

Confirm the pool is not imported by another host, the exact dataset tree and
mountpoints are understood, existing home contents are backed up, Tailscale
is enrolled or its bootstrap secret is available, the verified UID/GID values
match the intended existing home ownership, both `eno3` and `eno4` receive
DHCP leases through NetworkManager, Docker is usable but has no workloads,
and local console/recovery access is present. Do not run `zpool create`,
`zpool export`, `zpool labelclear`, `mkfs`, or destructive dataset commands as
preflight.

## Build, switch, and rollback

Build and inspect first:

```sh
nix flake check
nix build .#nixosConfigurations.r640-0.config.system.build.toplevel
sudo nixos-rebuild test --flake .#r640-0
sudo nixos-rebuild switch --flake .#r640-0
sudo nixos-rebuild switch --rollback
```

Keep local console/recovery access while testing. A VM can validate accounts,
sshd, Home Manager, and service ordering, but cannot prove the physical ZFS
pool, controller, dataset topology, or Tailscale control-plane enrollment.

## Secret provisioning

Create `/var/lib/host-age/keys.txt` and an encrypted
`/etc/nix-arbor/r640-0.sops.yaml` containing `ash_password_hash` and
`madeline_password_hash`, then enable `arbor.environment.secrets`. Never put
the age private key, password hashes, Tailscale auth key, or private SSH keys
in ordinary Nix source or the Nix store.
