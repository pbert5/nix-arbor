# Dendrites

This directory is the reusable capability tree for the main flake.

The shape is intentionally dendritic:

- top-level directories are capability families
- `dendrites/<parent>/dendrites/<child>/` contains one level of specialization
- entrypoints compose their own local leaves explicitly

## Families

- [`base/README.md`](/work/flake/dendrites/base/README.md)
- [`desktop/README.md`](/work/flake/dendrites/desktop/README.md)
- [`dev-tools/README.md`](/work/flake/dendrites/dev-tools/README.md)
- [`media/README.md`](/work/flake/dendrites/media/README.md)
- [`network/README.md`](/work/flake/dendrites/network/README.md)
- [`storage/README.md`](/work/flake/dendrites/storage/README.md)
- [`system/README.md`](/work/flake/dendrites/system/README.md)

## How To Read This Tree

If you want:

- shared host baseline, start at `base`
- desktop GUI behavior, start at `desktop`
- overlay transport and peer policy, start at `network`
- storage posture, start at `storage`
- high-level system class, start at `system`

Each family README links the current child dendrites and summarizes what that
branch is responsible for.
