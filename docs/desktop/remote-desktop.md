# Remote Desktop

`desktoptoodle` selects `system/workstation/remote-desktop`, which enables
Sunshine as a Moonlight-compatible streaming host.

The dendrite uses the native NixOS `services.sunshine` module. Sunshine starts
with the graphical user session, opens the module's declared firewall ports,
enables uinput, and grants the documented DRM/KMS capture capability.

Sunshine maps Right Alt to Windows/Super for Moonlight clients. This keeps
Hyprland shortcuts usable from Windows clients that capture the Windows key
locally; use Right Alt in place of Super while streaming. Laptop `Fn` keys are
usually handled before the OS sees keyboard input, so they are not a reliable
Moonlight/Sunshine remap target.

After rebuilding `desktoptoodle`, pair from a Moonlight client to
`desktoptoodle`. Use Sunshine's local web interface for pairing and application
management.
