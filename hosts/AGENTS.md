# Host Instructions

Apply these rules to host-specific override modules under `hosts/`.

- `hosts/` is for host-specific escape hatches only.
- Express reusable architecture through `inventory/hosts.nix` branch selection
  and dendrites/fruits, not through copied host-local behavior.
- Keep hosts behavior-light. Machine facts belong in `inventory/hosts.nix`
  under `facts`; consumed policy belongs under `org.*`.
- Host override entrypoints use explicit filenames matching their directory
  names, such as `hosts/r640-0/r640-0.nix`.
- Do not use `default.nix`.
- Build the affected host before handoff when changing host behavior. For
  `desktoptoodle`, prefer `rtk nixos-rebuild build --flake .#desktoptoodle`.
- Do not run `nixos-rebuild switch` unless the user explicitly grants
  deployment permission for that host.
