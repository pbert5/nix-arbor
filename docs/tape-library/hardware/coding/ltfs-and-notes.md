# Tape Coding Ltfs And Notes

## LTFS Notes

`ltfs-open` provides:

- `mkltfs` to format an LTFS cartridge
- `ltfs` to mount it through FUSE
- `ltfsck` to check or recover an LTFS volume

The tested Linux path for this IBM `ULT3580-HH5` drive is the upstream LTFS
reference implementation plus the generic SCSI device from `ltfs-default`.
`tape-default` resolves to `/dev/nst0`, which works for `mt` and `tar`, but
LTFS expects the matching `/dev/sg*` node instead.

On `t320-0`, the second drive is available through `tape-default-2` and
`ltfs-default-2`.

Explicit examples:

```bash
ltfs -o device_list
ltfs-default
ltfs-default-2
mkltfs -d "$(ltfs-default)" -n LTFS001
mkdir -p ~/mnt/ltfs
ltfs ~/mnt/ltfs -o devname="$(ltfs-default)"
umount ~/mnt/ltfs
```

The live `ltfs --help` output on `t320-0` currently reports
`-o sync_type=time@5` as the default, so LTFS attempts to write its index every
5 minutes during writes. LTFS also supports `-o sync_type=close` and
`-o sync_type=unmount` when you want different checkpoint behavior. Clean
unmount still matters, because that is the normal point where LTFS closes the
session and writes final metadata cleanly.

LTFS is the modern plan here because the current backup target is the `L5`
media set and the staged game-library workflow from the archived `tapelib`
notes. Raw `tar` remains available for legacy media and low-level inspection,
but it is not the primary game-library target anymore.

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
