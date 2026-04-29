# `desktop`

Desktop umbrella dendrite.

## Purpose

`desktop` is the parent branch for GUI workstation environments. It does not
currently set options on its own; it exists as a clean composition point for
desktop sub-dendrites.

## Current Children

- `desktop/cinnamon`
- `desktop/gnome`

## Selection

Select `desktop` only as a dependency anchor. In practice, hosts usually select
one of the child desktop environments instead.
