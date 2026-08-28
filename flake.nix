{
  description = "Nix Arbor: a small, composable Nix integration workspace";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    home-manager.url = "github:nix-community/home-manager";
    home-manager.inputs.nixpkgs.follows = "nixpkgs";
    sops-nix.url = "github:Mic92/sops-nix";
    sops-nix.inputs.nixpkgs.follows = "nixpkgs";
    flake-parts.url = "github:hercules-ci/flake-parts";
    flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs";
    ashzsh.url = "github:pbert5/AshZsh/b693b17";
    ashzsh.inputs.nixpkgs.follows = "nixpkgs";
    ashzsh.inputs.home-manager.follows = "home-manager";
    codex-switch.url = "github:pbert5/codex-switch";
    codex-switch.inputs.nixpkgs.follows = "nixpkgs";
    ashes-tools.url = "github:pbert5/AshesTools";
    ashes-tools.inputs.nixpkgs.follows = "nixpkgs";
    ashes-desktop-apps.url = "github:pbert5/AshDesktopApps";
    ashes-desktop-apps.inputs.nixpkgs.follows = "nixpkgs";
    tilingDesktop = {
      url = "github:pbert5/TilingDesktop";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.home-manager.follows = "home-manager";
    };
    arbor-manager.url = "github:pbert5/arbor-manager";
    arbor-registry.url = "github:pbert5/arbor-registry";
    arbor-network-manager.url = "github:pbert5/arbor-network-manager";
    yggdrasil-private.url = "git+https://github.com/pbert5/yggdrasil-private.git?ref=main";
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      imports = [
        ./modules/devshell.nix
        ./modules/checks.nix
        ./modules/apps.nix
        ./modules/components.nix
        ./config
      ];
    };
}
