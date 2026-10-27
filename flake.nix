{
  description = "Nix Arbor: a small, composable Nix integration workspace";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # Keep the Codex CLI refresh independent from unrelated host packages.
    # Update this exact pin deliberately when selecting a newer Codex release.
    codex-nixpkgs.url = "github:NixOS/nixpkgs/55bfb4d7437bd4e09ab7cba58a43bd68eb310044";
    home-manager.url = "github:nix-community/home-manager";
    home-manager.inputs.nixpkgs.follows = "nixpkgs";
    sops-nix.url = "github:Mic92/sops-nix";
    sops-nix.inputs.nixpkgs.follows = "nixpkgs";
    flake-parts.url = "github:hercules-ci/flake-parts";
    flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs";
    ashzsh.url = "github:pbert5/AshZsh/b693b17";
    ashzsh.inputs.nixpkgs.follows = "nixpkgs";
    ashzsh.inputs.home-manager.follows = "home-manager";
    # Direct Git transport avoids GitHub API access, which is unavailable for
    # this repository while retaining the same upstream and revision pin.
    codex-switch.url = "git+https://github.com/pbert5/codex-switch.git";
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
    arbor-registry.url = "github:pbert5/arbor-registry/e070aadb479b6a8ab9b38a49bc05df1f9b6fcd49";
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
