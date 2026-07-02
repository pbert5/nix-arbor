# Remote Desktop Workstation

`system/workstation/remote-desktop` enables Sunshine as a Moonlight-compatible
streaming host for interactive workstation machines.

## Main Effects

- enables `services.sunshine`
- starts Sunshine with the graphical user session
- opens Sunshine's NixOS-declared TCP and UDP firewall ports
- enables uinput through the upstream NixOS module
- grants Sunshine `CAP_SYS_ADMIN` for DRM/KMS screen capture
- publishes the host as `desktoptoodle`
- maps Right Alt to Windows/Super for Moonlight clients whose local system
  captures the Windows key

## Operator Notes

Pair from a Moonlight client to `desktoptoodle` after rebuilding the host.
Sunshine's local web interface can be used for pairing and application
management.

When streaming from Windows, use Right Alt in place of Super for Hyprland
shortcuts. For example, `Right Alt+Return` opens Kitty and `Right Alt+D` opens
Rofi. Laptop `Fn` keys are usually handled by keyboard firmware and may not be
visible to Moonlight or Sunshine as remappable input.
