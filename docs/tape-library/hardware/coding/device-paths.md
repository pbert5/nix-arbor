# Tape Coding Device Paths

## Current Hardware

`t320-0` is the host with the directly attached IBM TL2000 library.

The current hardware detected on May 19, 2026 is:

- Tape drives: dual IBM `ULT3580-HH5` firmware `E6Q3`
- Medium changer: IBM `3573-TL`
- Current media mix: `L5` target media plus visible legacy `L4` cartridges

## Repo Wiring

The `storage/tape` dendrite enables the shared tape feature from
[`dendrites/storage/dendrites/tape/tape.nix`](/work/flake/dendrites/storage/dendrites/tape/tape.nix).

That feature provides:

- Kernel modules: `sg`, `st`
- Tools: `bacula`, `gnutar`, `lsscsi`, `sg3_utils`, `mt`, `mtx`, `ltfs-open`,
  `tape-default`, `tape-default-2`, `ltfs-default`, `ltfs-default-2`,
  `changer-default`, selected LTFS manager, `stfs`
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
`org.storage.tape.yatm`. `t320-0` currently uses the shared tape substrate
without selecting a higher-level manager.

## Device Paths

Prefer the persistent `by-id` paths over raw `/dev/sg*` and `/dev/nst*` names
when you are writing scripts or want to target a specific device explicitly:

- Default changer helper: `changer-default`
- Default tape helper: `tape-default`
- Second tape helper: `tape-default-2`
- Default LTFS helper: `ltfs-default`
- Second LTFS helper: `ltfs-default-2`
- Changer: `/dev/tape/by-id/REPLACE_ME
- Tape drive `0`, non-rewinding: `/dev/tape/by-id/REPLACE_ME
- Tape drive `0`, rewinding: `/dev/tape/by-id/REPLACE_ME
- Tape drive `1`, non-rewinding: `/dev/tape/by-id/REPLACE_ME
- Tape drive `1`, rewinding: `/dev/tape/by-id/REPLACE_ME
- LTFS generic SCSI device for drive `0`: `/dev/sg6`
- LTFS generic SCSI device for drive `1`: `/dev/sg8`

Current discovery output on `t320-0`:

```text
[7:0:0:0] tape    IBM ULT3580-HH5 /dev/st0  /dev/sg6
[7:0:0:1] mediumx IBM 3573-TL     /dev/sch0 /dev/sg7
[7:0:1:0] tape    IBM ULT3580-HH5 /dev/st1  /dev/sg8
```

See the current short-name targets with:

```bash
changer-default
tape-default
tape-default-2
ltfs-default
ltfs-default-2
```

Use `lsscsi -g` when you want to map those helpers back to the hardware:

- `tape` rows are the drive and correspond to `/dev/st*` plus `/dev/nst*`.
- `ltfs-default` and `ltfs-default-2` resolve the matching drives to their
  `/dev/sg*` nodes for LTFS.
- `mediumx` rows are the changer and correspond to the generic SCSI node used by `mtx`.

## Terms

- Drive: the actual tape transport. The library currently reports two drives,
  numbered `0` and `1`.
- Slot: a storage position in the library. `mtx` numbers these from `1`.
- Import/export slot: the mailbox slot used to present or accept a cartridge.
  This library currently reports slot `24` as `IMPORT/EXPORT`.
- Volume tag: the barcode label the changer reads from the cartridge without
  mounting it. Example: `385182L5`.
- Tape file: a logical archive written to tape and separated by filemarks.
  Multiple `tar` archives can live on the same cartridge as separate tape
  files.
- `st`: the rewinding device. It usually rewinds automatically when the program
  closes the device.
- `nst`: the non-rewinding device. Use this for multi-step workflows and for
  storing multiple archives on one tape.

`L5` in the current target volume tags corresponds to LTO-5 media used by the
modern LTFS backup plan. Legacy `L4` media can still be visible in the library,
but it is not the current write target for the modern plan. The volume tag is
not a filesystem label and does not tell you what files are stored in the
archive.

## Rebuild

Apply the tape-access config with:

```bash
sudo nixos-rebuild switch --flake .#t320-0
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

- Drive `0` loaded from slot `12`
- Loaded volume tag in drive `0`: `385182L5`
- Drive `1` empty
- Import/export slot: `24`

Key `L5` tapes visible at that time:

- `12` -> loaded into drive `0` as `385182L5`
- `13` -> `430550L5`
- `14` -> `383685L5`
- `16` -> `384933L5`
- `17` -> `384333L5`
- `18` -> `384337L5`
- `19` -> `428857L5`
- `20` -> `426578L5`
- `21` -> `429414L5`
- `22` -> `426397L5`

Re-run `mtx status` before acting if you are depending on slot numbers.
