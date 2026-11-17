# raspberry-evolver

This is a headless Raspberry Pi 4 Model B configuration. Ethernet uses DHCP;
an optional selected NetworkManager Wi-Fi profile provides a backup. The Pi
enrolls in Tailscale on first boot and accepts SSH for the shared operator
public keys as `ash`. The Pioreactor HAT and Evolver application stack are
separate future work.

The image build and physical first boot have not yet been verified. In
particular, verify the image on the intended hardware before relying on it.

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

An x86 builder needs a working remote ARM builder or aarch64 emulation enabled
in NixOS and registered with Nix. On r640-0, the prepared host-only commit
`408c72e8941fe2ae8c53b749dce84610499076f7` adds
`boot.binfmt.emulatedSystems = [ "aarch64-linux" ];`. On 2026-11-17 the
primary checkout at `bb24db96a0876a9608011646efc09162c4dd8322` evaluated to
the running system, host preflight passed, and the modified system closure
built without activation. The operator subsequently activated this change on
r640-0, and the ARM smoke build below succeeded and reported `aarch64`.
Activation requires the operator's sudo credentials.

The supported r640 switch tool requires a clean primary `main` checkout. If
its state or the running system has changed since the checks above, reassess
the change before proceeding. Otherwise the operator can apply the isolated
host change and use the normal switch tool:

```sh
cd /home/ash/documents/nix-arbor
git status --short --branch
git rev-parse HEAD
git cherry-pick 408c72e8941fe2ae8c53b749dce84610499076f7
./tools/r640/switch --check
./tools/r640/switch --dry-run
./tools/r640/switch
```

The switch tool records the previous generation and prints its rollback
command, normally `sudo nixos-rebuild switch --rollback --flake
/home/ash/documents/nix-arbor#r640-0`. A rollback alone does not remove the
configuration change from Git; revert the host commit before a later switch
if ARM emulation is no longer wanted. After activation, verify actual ARM
execution from the takeover checkout before retrying the image:

```sh
cd /home/ash/documents/nix-arbor/.worktrees/raspberry-evolver-takeover
nix build --no-link --impure --expr 'let p = import (builtins.getFlake (toString ./.)).inputs.nixpkgs { system = "aarch64-linux"; }; in p.runCommand "arm-builder-smoke" {} "uname -m > $out"'
./tools/raspberry-evolver/image --build-only
```

The smoke command has succeeded on r640-0 after activation. Do not assume an
architecture listed in flake outputs means a builder can execute it.

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

Insert the card, connect Ethernet and power, and allow time for first boot.
Use your tailnet's machine list to check enrollment and an authorized operator
SSH key to connect. `./tools/raspberry-evolver/status --remote ash@HOST` gives
sanitized service and space status. `status --image IMAGE` inspects an image
and its manifest. If enrollment needs approval or a replacement key, see
[host recovery notes](../config/machines/raspberry-evolver/README.md).
The intended image grows its root filesystem on first boot; actual free space
and physical growth remain to be measured on the chosen card.

The flake check runs the image and flash tooling tests. The host bootstrap and
Nix retention fixtures run separately and require their local command
dependencies; they are not part of the sandboxed flake check:

```sh
bash tests/raspberry-evolver-host/bootstrap.sh
bash tests/raspberry-evolver-host/maintenance.sh
```
