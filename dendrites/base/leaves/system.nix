{ inputs, ... }:
{
  nixpkgs.config.allowUnfree = true;
  nixpkgs.overlays = [
    inputs.self.overlays.default
    (
      final: _prev: {
        unstable = import inputs.nixpkgs-unstable {
          inherit (final.stdenv.hostPlatform) system;
          config.allowUnfree = true;
        };
      }
    )
  ];

  programs.nix-ld.enable = true;

  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];
  nix.settings.download-buffer-size = 524288000;

  time.timeZone = "America/Chicago";

  system.stateVersion = "25.11";
}
