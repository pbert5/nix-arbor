# `network/tailscale`

Tailscale underlay network surface.

## Purpose

Turns on the Tailscale service for hosts that need the Tailscale underlay or
bootstrap transport.

## Main Effects

- enables `services.tailscale`

## Requirements

- requires `network`

## Notes

In the current cluster model, Tailscale is mainly the underlay and bootstrap
transport rather than the long-term east-west transport for the whole fleet.
