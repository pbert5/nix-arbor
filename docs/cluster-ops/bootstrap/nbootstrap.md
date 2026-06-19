# nbootstrap

`nbootstrap` is the umbrella bootstrap CLI for this repo.

It gives operators one command surface for the common bootstrap tasks while
keeping the dedicated tools available when you want the lower-level entrypoint.

## What It Covers

Today `nbootstrap` covers:

- live installer actions
- host enrollment
- the common "check SSH, then enroll, then optionally deploy" bootstrap flow

## Most Useful Commands

Build the live installer through the umbrella CLI:

```bash
nix run .#nbootstrap -- installer build
```

Write the live installer to a USB drive:

```bash
nix run .#nbootstrap -- installer write --device /dev/sdX
```

Run the raw enrollment flow:

```bash
nix run .#nbootstrap -- host enroll --host r640-0 --identity-file /home/example/.ssh/deploy_rsa --dry-run
```

Run the higher-level guided bootstrap flow:

```bash
nix run .#nbootstrap -- host bootstrap --host r640-0 --identity-file /home/example/.ssh/deploy_rsa --dry-run
```

That `host bootstrap` path does the extra operator-friendly step first:

1. resolve the target and SSH user from inventory if possible
2. run the basic `ssh ... 'hostname && whoami'` reachability check
3. hand off to the lower-level enrollment tool

## Which Entry Point To Prefer

Prefer these command shapes in normal operator work:

- `nix run .#live-installer`
  when you only need to build the installer image
- `nix run .#live-installer-usb -- --device /dev/sdX`
  when you want the USB-writing entrypoint directly
- `nix run .#nbootstrap -- host bootstrap ...`
  when you want the most guided host bootstrap path

Use `bootstrap-host` or `yggdrasil-bootstrap` when you specifically want the
lower-level enrollment tool itself.
