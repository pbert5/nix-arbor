# Hyprland Desktop

`desktoptoodle` selects the `desktop/hyprland` sub-dendrite. The branch keeps
the reusable NixOS and Home Manager parts together while leaving hardware and
host-only applications in `hosts/desktoptoodle/`.

## Minimal Branch

`desktop/hyprland-minimal` exists as a recovery-friendly branch so the
workstation can boot into a small Hyprland session while the richer desktop is
being debugged. It enables:

- Hyprland with XWayland and UWSM
- greetd with text `tuigreet`
- graphics, input, D-Bus, Polkit, and PipeWire audio basics
- Kitty, Rofi, a minimal Home Manager Hyprland config, workspace bindings,
  window controls, and media keys

It intentionally does not enable ReGreet, Waybar, wallpaper services,
Hyprlock, Hypridle, notification services, Bluetooth menus, printing,
removable-media helpers, or file-manager defaults.

Minimal controls:

| Binding | Action |
|---|---|
| `Super+Return` | open Kitty |
| `Super+D` | open Rofi |
| `Super+Q` | close the active window |
| `Super+Shift+E` | exit Hyprland |
| `Super+V` | toggle floating |
| `Super+F` | toggle fullscreen |
| `Super+1` through `Super+5` | select a workspace |
| `Super+Shift+1` through `Super+Shift+5` | move a window to a workspace |

## System Stack

The full `desktop/hyprland` NixOS side enables:

- Hyprland with XWayland and UWSM
- SDDM on Wayland with `hyprland-uwsm` as the default session
- `xdg-desktop-portal-hyprland`; the NixOS module also supplies the GTK
  fallback because the Hyprland portal does not implement a file picker
- PipeWire with ALSA, PulseAudio compatibility, and WirePlumber
- graphics, Bluetooth, Polkit, keyring, printing, removable-media, and power
  services
- PAM authentication for Hyprlock

The host's existing NVIDIA module keeps modesetting enabled. Hyprland's former
NVIDIA patch options are intentionally absent because current NixOS modules no
longer require them.

GDM is intentionally not enabled: upstream documents that it can crash
Hyprland on the first launch. SDDM is used as the graphical login manager for
the full branch, while the minimal branch keeps a text greeter for debugging.

## User Stack

The branch attaches one shared Home Manager module to users of a selected
host. It configures:

- Kitty as the terminal
- Rofi as the application launcher
- Waybar as a UWSM-managed user service with launcher, keybind-help,
  notifications, Bluetooth, network, tray, and power controls
- Hypridle with a ten-minute lock. The desktop does not automatically force
  monitor DPMS power-off while locked because that path has been fragile with
  Hyprlock on the current NVIDIA workstation stack.
- Hyprlock with a visible password prompt plus user and time labels
- `awww` as the wallpaper daemon, with restore-on-login and a Rofi wallpaper
  picker
- SwayNotificationCenter for notifications and a control-center panel
- `nm-applet` and `blueman-applet` in the tray for Wi-Fi and Bluetooth
- A Tailscale exit-node submenu inside the Wi-Fi menu for selecting, clearing,
  or inspecting exit nodes, including Mullvad-filtered choices when they are
  visible to the local Tailscale client. While an exit node is active, Waybar
  shows `vpn` and the exit node's hostname beside the normal network status.
  Yggdrasil's `200::/7` overlay route remains local when an exit node is active,
  so cluster services are not captured by Tailscale's IPv6 default route.
- Dolphin as the default handler for directories
- Shared desktop applications including Hydrus, GIMP, Anki, Google Chrome,
  KeePassXC, VLC, and LibreOffice
- A Hydrus submenu in the desktop menu. It scans known local Hydrus database
  roots, shows each discovered database version, launches with a pinned matching
  Hydrus package when available, and gives version hints for intermediate
  upgrades when a database is too old for the current package. The submenu can
  also prompt for a specific Hydrus version to launch or pin next. Hydrus clients
  launch normally and do not alter or require host-wide Tailscale routing.
  Each library can store its own Client API key from the Hydrus submenu. While
  that library is active, a user timer checks its open watcher pages every ten
  minutes and applies each watcher's subject as a `thread:` tag to imported
  media. Subjects are HTML-decoded, Unicode-normalized, stripped of control
  characters, and collapsed to single spaces. Existing `watcher:` mappings
  created by the earlier implementation are removed during migration. The timer
  is a no-op until a key has been configured. It connects to the local
  self-signed HTTPS API by default; `HYDRUS_API_URL` and
  `HYDRUS_TLS_VERIFY=1` can override the endpoint and require certificate
  verification.

Hydrus-specific packages, Client API automation, and enhanced wallpaper
rotation are owned by the separately selectable `desktop/hydrus` dendrite.
`desktop/hydrus/hydrui` adds HydrUI, a browser UI for Hydrus, as a child
specialization. It installs `hydrui-server`, runs it as a hardened systemd
service on the port declared by `inventory/ports.nix`, opens that port only on
the Tailscale firewall interface, and adds a HydrUI desktop/menu launcher for
the local session. The Hydrus library submenu can also open a selected library
in HydrUI by passing that library's saved Client API key and the configured
Hydrus API URL into HydrUI's setup hash.
The generic Hyprland branch owns only its desktop integration points and
focused Rofi leaves, including the Bluetooth and manual wallpaper menus.
- Google Chrome with a Home Manager desktop-entry override that launches
  `--new-window`, so app-menu launches do not bounce back to an existing Wayland
  window.
- Hyprpolkitagent as a graphical-session service
- GNOME Keyring's Secret Service component as a user service, which gives
  VS Code and other Electron/libsecret applications an OS keyring in Hyprland

The full branch pins the `desktoptoodle` desk layout by monitor description:
the LG UltraGear is the left display at `0x0`, and the Acer ED340CU is placed
to its right at `2560x0`. A fallback `,preferred,auto,1` rule remains for
unknown or temporary displays.

The wallpaper picker searches existing `~/Pictures/Wallpapers` and
`~/Pictures` directories, then sends the selected image to `awww`. If no cached
or local image is available, restore falls back to a dark `1e1e2eff`
background instead of black. Home Manager also bootstraps
`~/Pictures/Wallpapers` with `hyprland-demo-wallpaper.png` when that file is
absent, so a fresh desktop has a selectable demo wallpaper without replacing
user-managed images.

Both the full and minimal branches force ownership of
`~/.config/hypr/hyprland.conf` through Home Manager. Hyprland writes an
autogenerated stub there when no user config exists; replacing that stub during
activation is expected and prevents the session from starting with Hyprland's
fallback config.

The full branch also force-manages
`~/.local/share/applications/mimeapps.list`, which Home Manager generates from
`xdg.mimeApps`. This keeps stale backup files from blocking activation before
the Hyprland config is linked.

## Interactive VM

For fast playtesting on the same machine, `desktoptoodle` now defines a VM
variant through the dedicated flake app:

```bash
nix run .#host-vm -- desktoptoodle
```

The VM keeps its qcow state under `.vm-state/desktoptoodle/` by default, uses a
graphical QEMU window, and currently autologs straight into
`hyprland-uwsm` for faster iteration while the session is being stabilized.
Use `--fresh` to delete the saved qcow image and boot from a
clean VM disk again.

## Starter Controls

| Binding | Action |
|---|---|
| `Super+Return` | open Kitty |
| `Super+D` | open Rofi |
| `Super+Space` | open the Rofi desktop menu |
| `Super+W` | open the Wi-Fi menu |
| `Super+Shift+W` | open the wallpaper menu |
| `Super+B` | open the Bluetooth menu |
| `Super+N` | toggle the notification center |
| `Super+E` | open Dolphin |
| `Super+Escape` | open the power / logout menu |
| `Super+L` | lock the session |
| `Super+P` | toggle pseudotile for the focused window |
| `Super+Q` | close the active window |
| `Super+V` | toggle floating |
| `Super+F` | toggle fullscreen |
| `Super+Up` | toggle Hyprspace overview on the current display |
| `Super+Shift+Up` | toggle Hyprspace overview on all displays |
| `Super+PageDown` / `Super+PageUp` | switch to the next / previous open workspace |
| `Super+Shift+PageDown` / `Super+Shift+PageUp` | move a window to the next / previous open workspace |
| `Super+MouseWheel` | cycle open workspaces |
| `Super+Shift+Left`/`Right` or `Ctrl+Alt+Left`/`Right` | shift the workspace set between displays |
| `Super+Shift+Up` or `Ctrl+Alt+Up` | toggle Hyprspace's workspace overview on all displays |
| `Super+1` through `Super+5` | select a workspace |
| `Super+Shift+1` through `Super+Shift+5` | move a window to a workspace |

The desktop menu exposes:

- Applications
- Window switcher
- Dolphin
- Wallpaper picker
- Wi-Fi menu
- Bluetooth menu
- Notifications
- Keybind guide
- Power menu

The power menu now also includes:

- graceful logout through UWSM
- Waybar restart
- Hyprland config reload

Volume and microphone media keys use `wpctl`, so they control the same
PipeWire graph managed by WirePlumber.

## Version Note

The flake currently pins Hyprland 0.55.2. Home Manager is explicitly kept on
the native `hyprland.conf` generator because the users still have a 25.11 home
state version and the starter bindings use Hyprlang strings. Migrating this
module to Home Manager's Lua generator should be a separate, tested change.

## References

- [Hyprland on NixOS](https://wiki.hypr.land/Nix/Hyprland-on-NixOS/)
- [XDG Desktop Portal Hyprland](https://wiki.hypr.land/Hypr-Ecosystem/xdg-desktop-portal-hyprland/)
- [Hypridle](https://wiki.hypr.land/Hypr-Ecosystem/hypridle/)
- [Hyprlock](https://wiki.hypr.land/Hypr-Ecosystem/hyprlock/)
- [Wallpaper utilities](https://wiki.hypr.land/Useful-Utilities/Wallpapers/)
