# Tape Library

This is the short guide for the TL2000 on `desktoptoodle`.

It assumes the current single-library, single-drive setup and uses the tape
defaults from
[`dendrites/storage/dendrites/tape/tape.nix`](/work/flake/dendrites/storage/dendrites/tape/tape.nix):

- `mtx` works without `-f` because the wrapped command falls back to `changer-default`
- `mt` works without `-f` or `-t` because the wrapped command falls back to `tape-default`
- `changer-default` prints the exact changer path the short `mtx` form will use
- `tape-default` prints the exact non-rewinding tape path the short `mt` form will use
- `ltfs-default` prints the generic SCSI path LTFS tools should use by default

If you want the full explicit `by-id` paths, deeper hardware notes, or
script-oriented examples, use
[`docs/tape-library-coding-guide.md`](/work/flake/docs/tape-library-coding-guide.md).
For the higher-level apps layered on top of the base hardware commands, use
[`docs/tape-library/README.md`](/work/flake/docs/tape-library/README.md).
For LTFS-focused notes and upstream references, use
[`docs/tape-library/ltfs/README.md`](/work/flake/docs/tape-library/ltfs/README.md).

## Quick Commands

- `lsscsi -g`
  Show the tape drive, the changer, and their `/dev/sg*` mappings.
- `changer-default`
  Print the explicit changer path that `mtx` will use by default.
- `tape-default`
  Print the explicit non-rewinding tape path that `mt` will use by default.
- `ltfs-default`
  Print the generic SCSI path that `mkltfs`, `ltfs`, and `ltfsck` should use.
- `mtx status`
  Show the current slot map, loaded tape, and volume tags.
- `mtx inventory`
  Force the library to rescan what is in each slot.
- `mtx load <slot> 0`
  Load a tape from a slot into drive `0`.
- `mtx unload`
  Return the current tape to the slot it came from.
- `mt status`
  Show the current tape position and drive state.
- `mt rewind`
  Rewind the loaded tape.
- `mt eod`
  Go to end-of-data before appending another archive.
- `mt offline`
  Rewind and eject the loaded tape.
- `mt -f "$(tape-default)" status`
  Show the explicit form that matches the short `mt status` command.
- `mtx -f "$(changer-default)" status`
  Show the explicit form that matches the short `mtx status` command.
- `tar -tvf "$(tape-default)"`
  List the current tar archive on tape.
- `tar -cvf "$(tape-default)" /path/to/data`
  Write a tar archive to tape.
- `mkltfs -d "$(ltfs-default)" -n NAME`
  Format a tape for LTFS.
- `ltfs ~/mnt/ltfs -o devname="$(ltfs-default)"`
  Mount an LTFS tape at a directory.

## First Steps

If you just want to start using the library:

1. Rebuild and log back in so the `tape` group is active.
   Use `sudo nixos-rebuild switch --flake .#desktoptoodle`.
2. Run `lsscsi -g` to confirm the drive and changer are present.
3. Run `changer-default`, `tape-default`, and `ltfs-default` so you can see the
   exact device paths behind the short names.
4. Run `mtx status` to see what is loaded and which slots are full.
5. Run `mtx inventory` if the slot map looks stale.
6. Run `mt status` to confirm the drive is responding.

If you get `Permission denied`, the login session has not picked up the `tape`
group yet.

## Short Names

Use these when you want the short interactive commands:

```bash
changer-default
tape-default
ltfs-default
mtx status
mt status
```

If you want to spell the device out explicitly, use the helper commands inline:

```bash
mtx -f "$(changer-default)" status
mt -f "$(tape-default)" status
tar -tvf "$(tape-default)"
```

`lsscsi -g` helps you tell which is which:

- The tape drive row shows `tape` plus `/dev/st*`.
- The changer row shows `mediumx` plus the matching `/dev/sg*` node.

## Common Workflows

Check what is in the library:

```bash
mtx status
```

Load slot `12` into the drive:

```bash
mtx load 12 0
```

Inspect the tape that is loaded:

```bash
mt status
mt rewind
tar -tvf "$(tape-default)"
```

Extract the current archive:

```bash
mkdir -p /tmp/tape-restore
mt rewind
tar -xvf "$(tape-default)" -C /tmp/tape-restore
```

Write a new tar archive:

```bash
mt rewind
tar -cvf "$(tape-default)" /path/to/data
```

Append another tar archive:

```bash
mt eod
tar -cvf "$(tape-default)" /path/to/next-dataset
```

Finish and put the tape back:

```bash
mt offline
mtx unload
mtx status
```

## LTFS

Use LTFS when you want a mounted filesystem view instead of a raw tar stream.
On this host, LTFS uses the drive's generic SCSI node instead of the
non-rewinding tape path that `mt` and `tar` use.

Format a tape for LTFS:

```bash
mkltfs -d "$(ltfs-default)" -n LTFS001
```

Mount it:

```bash
mkdir -p ~/mnt/ltfs
ltfs ~/mnt/ltfs -o devname="$(ltfs-default)"
```

Unmount it cleanly when you are done:

```bash
umount ~/mnt/ltfs
```

The current `ltfs` build on this host reports the default mount behavior as
`-o sync_type=time@5`, so LTFS attempts to checkpoint its index to tape every
5 minutes while writes are active. A clean `umount` also writes the current
metadata before the session ends.

Use `ltfs-default` first if you want to confirm which exact device LTFS is
about to open. `tape-default` is still the right helper for `mt` and `tar`.
If you need an explicit `by-id` path or recovery tools such as `ltfsck`, the
coding guide has the longer forms.

## Switching Between Raw Tape And LTFS

When you switch workflows, treat LTFS and raw tape access as separate modes:

1. For raw tape to LTFS:
   stop using `mt`, `tar`, `stfs`, `fossilsafe`, or `yatm`, then mount LTFS
   with `ltfs-default`.
2. For LTFS back to raw tape:
   run `umount <mountpoint>`, wait for the `ltfs` process to finish, and only
   then return to `mt`, `tar`, or other raw tape tools.
3. Do not run `mt`, `tar`, or changer-manager workflows against a drive that is
   currently mounted through LTFS.

## More Detail

- Use `mtx status` as the source of truth for slot numbers and barcodes.
- Use the non-rewinding drive for multi-step work so tape position does not
  reset between commands.
- Run `changer-default` and `tape-default` when you want the exact path behind
  the short commands.
- Run `ltfs-default` when you want the exact generic SCSI node behind LTFS.
- Use `mt offline` before `mtx unload` if the library refuses to grab the tape.
- Use
  [`docs/tape-library-coding-guide.md`](/work/flake/docs/tape-library-coding-guide.md)
  when you want exact device paths, import/export slot notes, or scripting
  examples.
- Use [`docs/tape-library/README.md`](/work/flake/docs/tape-library/README.md)
  when you want the packaged `fossilsafe`, `yatm`, and `stfs` workflows, or the
  current host-level LTFS-manager selection.
