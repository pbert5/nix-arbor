# STFS

Local package: `stfs`

## What It Is For

- Tar-oriented tape workflows
- Direct archive operations against `/dev/nst*`
- Older non-LTFS media, especially LTO-4

## Local Packaging

- Repo-local package under
  [`dendrites/storage/dendrites/tape/_packages/stfs.nix`](/work/flake/dendrites/storage/dendrites/tape/_packages/stfs.nix)
- Built from upstream source tag `v0.1.1`

## Quick Start

Use the non-rewinding tape device:

```bash
stfs serve ftp -d "$(tape-default)" -m ~/.local/share/stfs/metadata.sqlite
```

Or initialize a direct tape archive:

```bash
stfs operation initialize -d "$(tape-default)" -m ~/.local/share/stfs/metadata.sqlite
```

STFS is the cleanest fit in this stack when the tape is not LTFS-formatted and
we want a filesystem-like layer over tar records instead.
