# New Host From Live Installer

This is the step-by-step operator playbook for taking a machine from "blank box
with a USB stick" to "leader can manage it over SSH and the repo knows its
identity."

If you want the shortest version:

1. build the USB
2. boot the target
3. confirm root SSH from a leader
4. run `nbootstrap -- host bootstrap --dry-run`
5. run the real bootstrap command
6. do the first deployment

The rest of this page expands each step and tells you what to look for.

## Before You Start

Make sure all of these are true before touching the target:

1. the host exists in
   [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix)
2. the host has bootstrap metadata in
   [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
   or you already know the temporary target IP you will pass with `--target`
3. you are sitting on a trusted leader machine, or another machine that has the
   correct leader private key locally
4. you know which block device is the USB stick on the machine that will write
   the installer image

If any of that is missing, stop and fix it first. It is much easier to correct
inventory or key placement before the target is involved.

## Step 1: Build The Live Installer

Run:

```bash
nix run .#live-installer
```

What success looks like:

- the command exits cleanly
- it prints a `Build output:` path
- it prints an `Image file:` path ending in `.iso`

If you only want the image path:

```bash
nix run .#live-installer -- --print-image-path
```

## Step 2: Write The USB Stick

Run:

```bash
nix run .#live-installer-usb -- --device /dev/sdX
```

Replace `/dev/sdX` with the real USB block device.

Pause here and double-check the device name before pressing Enter. This command
overwrites the device you point it at.

What success looks like:

- `dd` runs without error
- the command prints `Wrote ... to /dev/sdX`

## Step 3: Boot The Target From The USB

On the target machine:

1. insert the USB stick
2. select it as the boot device
3. wait for the live environment to finish booting
4. connect the machine to the network if it is not already connected
5. determine the target's temporary IP address

What success looks like:

- the machine is sitting in the NixOS live environment
- the network is up
- you know the IP you can SSH to from a leader

## Step 4: Verify Leader Root SSH

From a trusted leader machine, run:

```bash
ssh -i /path/to/private/key root@TARGET_IP 'hostname && whoami'
```

What success looks like:

- the command prints the remote hostname
- the command prints `root`

If this fails, do not continue yet. Fix raw reachability first.

Useful places to inspect next:

- target IP correctness
- switch port or Wi-Fi state
- whether the leader private key matches one of the public keys in
  [`inventory/keys/leaders/`](/work/flake/inventory/keys/leaders)

## Step 5: Run The Dry-Run Bootstrap

Now ask the repo what it sees before making inventory changes:

```bash
nix run .#nbootstrap -- \
  host bootstrap \
  --host r640-0 \
  --target TARGET_IP \
  --identity-file /path/to/private/key \
  --dry-run
```

What this does:

1. resolves the bootstrap connection settings
2. runs the SSH reachability check for you
3. reads or generates the host's Ygg identity
4. prints the discovered public key and address without rewriting inventory

What success looks like:

- the command prints the resolved bootstrap connection data
- the command prints discovered `publicKey`
- the command prints discovered `address`

If the IP, SSH user, or key looks wrong, fix that now and rerun the dry run.

## Step 6: Run The Real Bootstrap

Once the dry run looks good, rerun without `--dry-run`:

```bash
nix run .#nbootstrap -- \
  host bootstrap \
  --host r640-0 \
  --target TARGET_IP \
  --identity-file /path/to/private/key
```

What this changes:

- [`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
- [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)

What success looks like:

- the command reports both files as updated
- the host now has enrolled `address` and `publicKey`

## Step 7: Do The First Deployment

If you want the first deployment as part of bootstrap, use:

```bash
nix run .#nbootstrap -- \
  host bootstrap \
  --host r640-0 \
  --target TARGET_IP \
  --identity-file /path/to/private/key \
  --deploy-tool deploy-rs
```

That keeps the whole "verify, enroll, first deploy" path under one operator
command.

What success looks like:

- bootstrap completes
- `deploy-rs` or `colmena` reports a successful activation

## Step 8: Decide Whether To Stay On Bootstrap Transport Or Switch To Ygg

Right after first contact, it is fine to keep a host on bootstrap transport for
a bit.

When you are ready to promote normal management to Ygg, run:

```bash
nix run .#nbootstrap -- \
  host enroll \
  --host r640-0 \
  --identity-file /path/to/private/key \
  --deployment-transport privateYggdrasil \
  --deploy-tool deploy-rs
```

Then inspect the generated deploy target:

```bash
nix eval '.#deploy.nodes.r640-0' --json
```

What success looks like:

- the generated deploy hostname now prefers the logical host entry for Ygg
- the follow-up deployment succeeds

## Step 9: If You Need A Persistent Disk Install

The current live-installer workflow does not fully automate per-host disk
layout or a universal `nixos-install` step yet.

Treat the live installer as the remote-control and bootstrap environment. If
the target also needs a persistent NixOS install on disk, do that as a separate
explicit operator action after deciding the disk layout for that host.

In other words:

- the live installer gets you a manageable machine
- `nbootstrap` gets the repo and trust graph updated
- persistent disk install remains deliberate and host-specific for now

## If You Get Stuck

Read these next:

- [`live-installer.md`](/work/flake/docs/cluster-ops/bootstrap/live-installer.md)
- [`bootstrap-host.md`](/work/flake/docs/cluster-ops/bootstrap/enrollment/bootstrap-host.md)
- [`troubleshooting.md`](/work/flake/docs/cluster-ops/reference/troubleshooting.md)
