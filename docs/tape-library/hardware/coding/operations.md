# Tape Coding Operations

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
