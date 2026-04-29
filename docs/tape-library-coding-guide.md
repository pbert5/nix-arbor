# Tape Library Coding Guide

Use this guide when you want the explicit device paths, the longer command
forms, or the hardware-specific details for `desktoptoodle`.

If you just want to start using the library, use
[`docs/tape-library.md`](/work/flake/docs/tape-library.md) first.

## Current Hardware

`desktoptoodle` is the host with the directly attached IBM TL2000 library.

The current hardware detected on April 19, 2026 is:

- Tape drive: IBM `ULT3580-HH5` firmware `E6Q3`
- Medium changer: IBM `3573-TL`
- Tape generation in the library: LTO-5

## Repo Wiring

The `storage/tape` dendrite enables the shared tape feature from
[`dendrites/storage/dendrites/tape/tape.nix`](/work/flake/dendrites/storage/dendrites/tape/tape.nix).

That feature provides:

- Kernel modules: `sg`, `st`
- Tools: `bacula`, `gnutar`, `lsscsi`, `sg3_utils`, `mt`, `mtx`, `ltfs-open`,
  `tape-default`, `ltfs-default`, `changer-default`, selected LTFS manager,
  `stfs`
- Tape defaults:
  `mtx` works without `-f` because the wrapped command falls back to the path
  printed by `changer-default`.
  `mt` works without `-f`/`-t` because the wrapped command falls back to the
  path printed by `tape-default`.
  `mkltfs`, `ltfs`, and `ltfsck` should use the generic SCSI path printed by
  `ltfs-default`.

`user1` is also granted membership in the `tape` group on hosts tagged
`tape-library`. After rebuilding, start a new login session before testing so
the new group takes effect.

## Companion Apps

The packaged higher-level tools now live under
[`docs/tape-library/README.md`](/work/flake/docs/tape-library/README.md):

- `fossilsafe`
  LTFS archive workflow with UI, CLI, and smoke test
- `stfs`
  Tar-oriented tape filesystem layer for direct tape workflows and LTO-4 media
- `yatm`
  Dedicated LTFS browser and job UI

The active LTFS manager is selected per host in
[`inventory/hosts.nix`](/work/flake/inventory/hosts.nix) using
`org.storage.tape.manager`. Host-specific FossilSafe settings live under
`org.storage.tape.fossilsafe`, and host-specific YATM settings live under
`org.storage.tape.yatm`. `desktoptoodle` is currently set to `fossilsafe`.

## Device Paths

Prefer the persistent `by-id` paths over raw `/dev/sg2` and `/dev/nst0` names
when you are writing scripts or want to target a specific device explicitly:

- Default changer helper: `changer-default`
- Default tape helper: `tape-default`
- Default LTFS helper: `ltfs-default`
- Changer: `/dev/tape/by-id/REPLACE_ME
- Tape drive, non-rewinding: `/dev/tape/by-id/REPLACE_ME
- Tape drive, rewinding: `/dev/tape/by-id/REPLACE_ME
- LTFS generic SCSI device: `/dev/sg1`

Current discovery output on `desktoptoodle`:

```text
[0:0:0:0] tape    IBM ULT3580-HH5 /dev/st0  /dev/sg1
[0:0:0:1] mediumx IBM 3573-TL     /dev/sch0 /dev/sg2
```

See the current short-name targets with:

```bash
changer-default
tape-default
ltfs-default
```

Use `lsscsi -g` when you want to map those helpers back to the hardware:

- `tape` rows are the drive and correspond to `/dev/st*` plus `/dev/nst*`.
- `ltfs-default` resolves that same drive to its `/dev/sg*` node for LTFS.
- `mediumx` rows are the changer and correspond to the generic SCSI node used by `mtx`.

## Terms

- Drive: the actual tape transport. The library currently reports one drive,
  numbered `0`.
- Slot: a storage position in the library. `mtx` numbers these from `1`.
- Import/export slot: the mailbox slot used to present or accept a cartridge.
  This library currently reports slot `24` as `IMPORT/EXPORT`.
- Volume tag: the barcode label the changer reads from the cartridge without
  mounting it. Example: `000006L4`.
- Tape file: a logical archive written to tape and separated by filemarks.
  Multiple `tar` archives can live on the same cartridge as separate tape
  files.
- `st`: the rewinding device. It usually rewinds automatically when the program
  closes the device.
- `nst`: the non-rewinding device. Use this for multi-step workflows and for
  storing multiple archives on one tape.

`L4` in the current volume tags corresponds to LTO-4 media already loaded in
the library. The drive itself is now LTO-5 capable. The volume tag is not a
filesystem label and does not tell you what files are stored in the archive.

## Rebuild

Apply the tape-access config with:

```bash
sudo nixos-rebuild switch --flake .#desktoptoodle
```

Then log out and back in, or start a fresh login shell, and confirm:

```bash
id -nG | tr ' ' '\n' | rg '^tape$'
```

## Explicit Inspection

List the drive and changer:

```bash
lsscsi -g
```

Ask the changer what it currently sees:

```bash
changer-default
mtx -f /dev/tape/by-id/REPLACE_ME
```

Force a fresh scan of slots and then print status again:

```bash
changer-default
mtx -f /dev/tape/by-id/REPLACE_ME
mtx -f /dev/tape/by-id/REPLACE_ME
```

Ask the tape drive about the loaded cartridge and current tape position:

```bash
tape-default
mt -f /dev/tape/by-id/REPLACE_ME
```

If either `mtx` or `mt` says `Permission denied`, the login session has not yet
picked up the `tape` group.

## Current Library Snapshot

The most recent live `mtx status` output showed:

- Drive `0` loaded from slot `17`
- Loaded volume tag: `000006L4`
- Import/export slot: `24`

Full slots visible at that time:

- `1` -> `000031L4`
- `12` -> `000001L4`
- `13` -> `000002L4`
- `14` -> `000003L4`
- `15` -> `000004L4`
- `16` -> `000005L4`
- `18` -> `000007L4`
- `19` -> `000008L4`
- `20` -> `000009L4`
- `21` -> `000010L4`
- `22` -> `000012L4`
- `23` -> `000029L4`

Re-run `mtx status` before acting if you are depending on slot numbers.

## Moving Cartridges

Load a cartridge from slot `12` into drive `0`:

```bash
mtx -f /dev/tape/by-id/REPLACE_ME
```

Unload the tape in drive `0` back to slot `12`:

```bash
mtx -f /dev/tape/by-id/REPLACE_ME
```

Unload the tape back to the slot it originally came from:

```bash
mtx -f /dev/tape/by-id/REPLACE_ME
```

Move a cartridge directly from one storage slot to another:

```bash
mtx -f /dev/tape/by-id/REPLACE_ME
```

The `exchange` command is the closest CLI equivalent to swapping cassettes in
place. Be careful with it and verify the slot map before running it.

## Import And Export Slot

This library reports slot `24` as the import/export slot.

Move a cartridge from storage slot `12` to the mailbox:

```bash
mtx -f /dev/tape/by-id/REPLACE_ME
```

Move a cartridge from the mailbox back into storage slot `12`:

```bash
mtx -f /dev/tape/by-id/REPLACE_ME
```

Some libraries require front-panel interaction to physically open or acknowledge
the mailbox. `mtx` also has library-specific `eepos` support, but that behavior
was not verified on this TL2000 and should be treated as advanced vendor-
specific behavior.

## Tape Positioning

Rewind the loaded tape:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
```

Eject or offline the loaded tape:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
```

Move forward one tape file:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
```

Move backward one tape file:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
```

Go to end-of-data before appending a new archive:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
```

Write an extra filemark manually:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
```

Some additional `mt` features such as `tell` and `seek` are drive-dependent.
Use them as investigation tools only after confirming support on this hardware.

## Reading Tape Contents

To list the first tar archive on the loaded tape:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
tar -tvf /dev/tape/by-id/REPLACE_ME
```

To extract the first tar archive:

```bash
mkdir -p /tmp/tape-restore
mt -f /dev/tape/by-id/REPLACE_ME
tar -xvf /dev/tape/by-id/REPLACE_ME
```

To inspect the second archive on a tape:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
mt -f /dev/tape/by-id/REPLACE_ME
tar -tvf /dev/tape/by-id/REPLACE_ME
```

To inspect the third archive, skip two files instead of one.

## Writing With Tar

Write one tar archive to a freshly loaded tape:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
tar -cvf /dev/tape/by-id/REPLACE_ME
```

Append a second tar archive to the same tape:

```bash
mt -f /dev/tape/by-id/REPLACE_ME
tar -cvf /dev/tape/by-id/REPLACE_ME
```

Capture a compressed stream explicitly:

```bash
tar -czvf /dev/tape/by-id/REPLACE_ME
```

Compression here is done in software before bytes hit the tape. Keep in mind
that already-compressed data usually gains little and may slow writes down.

## LTFS Notes

`ltfs-open` provides:

- `mkltfs` to format an LTFS cartridge
- `ltfs` to mount it through FUSE
- `ltfsck` to check or recover an LTFS volume

The tested Linux path for this IBM `ULT3580-HH5` drive is the upstream LTFS
reference implementation plus the generic SCSI device from `ltfs-default`.
`tape-default` resolves to `/dev/nst0`, which works for `mt` and `tar`, but
LTFS expects the matching `/dev/sg*` node instead.

Explicit examples:

```bash
ltfs -o device_list
ltfs-default
mkltfs -d "$(ltfs-default)" -n LTFS001
mkdir -p ~/mnt/ltfs
ltfs ~/mnt/ltfs -o devname="$(ltfs-default)"
umount ~/mnt/ltfs
```

The live `ltfs --help` output on `desktoptoodle` currently reports
`-o sync_type=time@5` as the default, so LTFS attempts to write its index every
5 minutes during writes. LTFS also supports `-o sync_type=close` and
`-o sync_type=unmount` when you want different checkpoint behavior. Clean
unmount still matters, because that is the normal point where LTFS closes the
session and writes final metadata cleanly.

LTFS is great when you want drag-and-drop style file access. Raw `tar` is still
the simpler choice when you want a single archive stream and very explicit tape
position control.

## Switching Between Raw Tape And LTFS

Switching cleanly matters more than the exact command spelling:

1. Raw tape to LTFS:
   make sure `mt`, `tar`, `stfs`, `fossilsafe`, and `yatm` are not touching the
   drive, then mount LTFS with the SG device from `ltfs-default`.
2. LTFS to raw tape:
   run `umount <mountpoint>` and wait for the `ltfs` process to exit before
   touching `tape-default` again.
3. If you need a stronger checkpoint policy during LTFS writes, add
   `-o sync_type=close` when mounting. If you want fewer sync writes, set
   another `time@N` interval explicitly.

## Investigation Tips

- `mtx inquiry` reports the changer identity and API style.
- `mtx status` is your source of truth for slot occupancy and volume tags.
- `mt status` tells you the current file number, block number, and density code.
- `tar -tvf` is the safest first check when you suspect a tape contains a tar
  archive.
- If you lose track of tape position while reading, rewind and start again.
- If `mtx unload` fails after a read or write, try `mt offline` first and then
  unload the tape from the changer.

## Notes

- Use the non-rewinding `nst` device for multi-step workflows.
- Re-run `inventory` if the library's slot view looks stale.
- The volume tag is physical media identification, not a catalog of stored
  files.
- This repo currently provides local tape tooling and direct CLI workflows, not
  a complete backup policy or a higher-level tape catalog.
