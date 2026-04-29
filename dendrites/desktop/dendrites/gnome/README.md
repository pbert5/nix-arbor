# `desktop/gnome`

GNOME desktop environment for workstation-class hosts.

## Purpose

Provides the GNOME graphical stack on top of the `desktop` parent dendrite.

## Main Effects

- enables X11
- enables GDM
- enables GNOME desktop services and keyring support
- enables Bluetooth, graphics, PipeWire, printing, GVFS, and related desktop
  services

## Requirements

- requires `desktop`
- conflicts with `desktop/cinnamon`
- intended for `workstation` hosts
