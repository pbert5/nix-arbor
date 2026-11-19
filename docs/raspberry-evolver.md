# raspberry-evolver

This is a headless Raspberry Pi 4 Model B configuration. Ethernet uses DHCP;
an optional selected NetworkManager Wi-Fi profile provides a backup. The Pi
enrolls in Tailscale on first boot and accepts SSH for the shared operator
public keys as `ash`. The Pioreactor HAT and Evolver application stack are
separate future work.

The local login screen shows IPv4 and IPv6 addresses before anyone signs in.
Connect Ethernet and wait for DHCP. The prompt refreshes when the address
changes. From another machine on the same network, use `ssh ash@<IP>`.

## Build and personalize

From a committed Nix Arbor checkout on a machine with a working aarch64 Nix
builder and enough free disk space:

```sh
./tools/raspberry-evolver/doctor
./tools/raspberry-evolver/image
```

Once the build finishes, paste the Tailscale Linux install command or just its
auth key at the hidden prompt. The tool extracts the key as data; it never
executes the pasted command. Prefer a fresh single-use, non-ephemeral key for
each image. Account approval, key expiry and Tailnet Lock can still require
operator action. Do not paste a real key into chat, Git or a shell command.

For Wi-Fi, select one simple WPA-PSK NetworkManager profile from the source
machine. Put a private, owner-only copy somewhere outside the checkout and
pass it with `--wifi-file /path/to/profile.nmconnection`. The profile must
contain its saved PSK and be readable by the operator; the tool removes
source interface and connection identities and configures DHCP. It does not
support enterprise Wi-Fi or external certificates. Delete the private copy
when finished. Ethernet does not require this profile.

On the machine that has the saved Wi-Fi connection, use the filename of the
selected profile. With the clean image and manifest present on that machine:

```sh
nmcli -f NAME,TYPE,FILENAME connection show
private=$(mktemp -d)
sudo install -m 0600 -o "$(id -u)" -g "$(id -g)" -- /path/to/selected.nmconnection "$private/backup.nmconnection"
./tools/raspberry-evolver/image --from /path/to/clean.img --wifi-file "$private/backup.nmconnection"
rm -- "$private/backup.nmconnection"
rmdir -- "$private"
```

To build and personalize on different machines, run `image --build-only` on
the builder, securely copy the printed clean image **and its adjacent `.json`
manifest** to the operator machine, and run:

```sh
./tools/raspberry-evolver/image --from /path/to/clean.img --wifi-file /path/to/profile.nmconnection
```

Omit `--wifi-file` when no Wi-Fi backup is needed. Build outputs and private
copies live outside the repository under `${XDG_STATE_HOME:-$HOME/.local/state}/raspberry-evolver`.
The personalized image and any copies contain credentials, even after a Pi
boots; protect and dispose of them accordingly. Deleting a file does not
guarantee secure erasure.

Keep the clean image and manifest together. For each additional card, run
`image --from` on that pair with a fresh Tailscale key. This skips both Nix
evaluation and image assembly.

### Building on r640-0

r640-0 already has working AArch64 emulation. Run the build from the committed
Pi checkout. This command limits parallelism on the shared host:

```sh
cd /home/ash/documents/nix-arbor/.worktrees/raspberry-evolver-takeover
NIX_CONFIG='cores = 8
max-jobs = 4' ./tools/raspberry-evolver/image --build-only
```

The normal Nix cache lacks this BCM2711 kernel. Compiling it under QEMU ran
for over two hours on eight cores. With the current pin, Nix fetches the two
runtime outputs from the Raspberry Pi Cachix cache and verifies their unpacked
hashes. The Pi image uses ext4 and FAT, so it also skips the external ZFS
module. Fetching and verifying both archives in an empty store took 2m 08s
on r640-0. On x86, the image tool runs ext4 creation, partitioning and
compression natively. An ARM builder or emulation prepares the Pi system and
boot files. On ARM the tool uses the standard upstream SD image directly.

On a different builder, this smoke test builds and prints its architecture:

```sh
cat "$(nix build --no-link --print-out-paths --impure --expr 'let p = import (builtins.getFlake (toString ./.)).inputs.nixpkgs { system = "aarch64-linux"; }; in p.runCommand "arm-builder-smoke" {} "uname -m > $out"')"
```

The r640-0 smoke build printed `aarch64` after the operator activated
`boot.binfmt.emulatedSystems = [ "aarch64-linux" ];` (host change
`408c72e`). For recovery, use the previous generation recorded by
`./tools/r640/switch`. Revert the host change in the primary checkout before
a subsequent switch if you want emulation removed.

When updating the Pi kernel, `kernel-cache.nix` compares the evaluated upstream
output path, including configured patches, to the recorded pin. A changed
kernel uses the upstream build and emits a warning. Before refreshing the
pins, verify both upstream store paths with `nix store verify --store
https://nixos-raspberrypi.cachix.org --option trusted-public-keys KEY
--sigs-needed 1 OUT MODULES`, using the public key in the locked upstream
flake. Both narinfos must have empty `References` for this technique. Record
their URLs and `NarHash` values, then check the SD image with
`nix build --dry-run .#raspberry-evolver-image`.

## Write and boot

The writer supports native MMC/SD readers exposing the card CID and removable
USB readers with a usable reader serial and Linux disk sequence. A USB serial
identifies the reader, not the card; some readers do not report card changes.
Do not remove or swap the card between inspection and the end of verification.
Readers without the required identifiers or a removable-device flag are refused.
Raspberry Pi Imager's
custom-image option is an alternative; independently verify its selected card.
The physical card is erased by a confirmed write. Inventory and inspect first:

```sh
./tools/raspberry-evolver/flash
./tools/raspberry-evolver/flash /path/to/personalized.img /dev/mmcblkX
./tools/raspberry-evolver/flash /path/to/personalized.img /dev/mmcblkX --write
```

Replace the device with the independently identified whole SD card. The last
command requests privileged inspection and then requires the exact printed
device identity and size. It refuses mounted or conflicting devices and checks
the written byte range. It does not unmount devices or prove the Pi will boot.

Insert the card in the Pi 4B, attach Ethernet and power it on. Confirm
`raspberry-evolver` appears in the intended tailnet, then run:

```sh
./tools/raspberry-evolver/status --remote ash@raspberry-evolver
ssh ash@raspberry-evolver 'lsblk -b -o NAME,SIZE,MOUNTPOINTS; df -h /; ip -4 route show default'
```

Use the Pi's LAN address for SSH if tailnet DNS or enrollment is pending.
To verify Wi-Fi backup, unplug Ethernet, reconnect over Tailscale and check
the default route again. Reconnect Ethernet and confirm the preferred route
returns. For approval or key replacement, see the
[host recovery notes](../config/machines/raspberry-evolver/README.md).

The flake check runs the image and flash tooling tests. The host bootstrap and
Nix retention fixtures run separately and require their local command
dependencies; they are not part of the sandboxed flake check:

```sh
bash tests/raspberry-evolver-host/bootstrap.sh
bash tests/raspberry-evolver-host/maintenance.sh
```

## Thin MVP image

A clean image built with `image --build-only --thin-release RELEASE-DIRECTORY`
includes a Git bundle, Docker image archive and revision/image-ID manifest.
The first boot imports that release locally as `ash` and starts thin after
PostgreSQL is ready, roles exist and migrations pass. The imported archive is
removed after verification. The editable checkout is `/home/ash/evolver`.
An ordinary boot uses the prepared images with pulls and builds disabled.

1. Flash the clean image to a fresh SD card using the drive-selection safeguards
   above. Keep the old card available for rollback.
2. On Windows, open the visible `FIRMWARE` partition. Save one raw auth key as
   `tailscale-authkey.txt` at its root and eject the card. Verify Windows did not
   append a second `.txt`. Use a short-lived, one-use, non-ephemeral key.
3. Connect Ethernet and boot. The Pi mounts the partition at `/boot/firmware`.
   The HDMI login prompt shows LAN and Tailscale addresses as they become
   available. Use the existing SSH key with `ssh ash@ADDRESS`.
4. If enrollment needs attention, check
   `cat /run/raspberry-evolver/bootstrap.status` over LAN SSH. With no key file,
   use `sudo tailscale up --accept-dns=false`. For an expired or rejected key,
   shut down and replace the file. A retained key on FAT is plaintext. Deleting
   it after enrollment does not securely erase it.
5. Review the startup log with
   `journalctl -u raspberry-evolver-install-thin -u raspberry-evolver-thin -b`.
   Run `cd ~/evolver && ./tools/thin/status`. Forward the UI through SSH with
   `ssh -L 18086:127.0.0.1:18086 ash@ADDRESS` and browse to
   `http://localhost:18086`. In VS Code use Remote-SSH with the same host and
   open `/home/ash/evolver`.

Fresh releases disable automatic instrument discovery. Existing thin data
volumes can retain operating settings across starts. Review them before
connecting instruments. `./tools/thin/down` records a stop across reboots and
`./tools/thin/up` resumes operation. `./tools/dev-env up` and
`./tools/dev-env shell` are explicit development operations. ARM64 omits the
pinned firmware build/upload toolchain.

For an update, back up the database and runtime volumes, record the previous
checkout and matching image IDs, commit changes and prepare the replacement
images off the Pi. Load them on the Pi and install the matching
`var/state/thin-images` manifest before running `./tools/thin/up`. Keep the
previous release artifacts. Roll back with the previous checkout, images and
manifest, and restore the matching database backup if migrations changed it.
For a failed first boot, preserve the new card for logs and reinsert the
previous card with the Pi powered off.
