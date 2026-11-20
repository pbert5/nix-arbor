{ inputs, self, ... }:
let
  networkPolicy = import ./networks.nix;
  sshAgent = import ./modules/ssh-agent.nix;
  r640Users = import ./users;
  r640Env = import ./env.nix;
  vscodeRemoteModule = import ./modules/vscode-remote.nix;
  vscodeRemote = [ vscodeRemoteModule ];
  serverTools =
    { pkgs, ... }:
    {
      environment.systemPackages = with pkgs; [
        git
        gh
        curl
        wget
        devcontainer
        jq
        yq-go
        ripgrep
        fd
        fzf
        tmux
        btop
        vim
        neovim
        rsync
        openssh
        nixfmt-rfc-style
        nil
        nix-tree
        nh
        tailscale
        zfs
        inputs.codex-nixpkgs.legacyPackages.${pkgs.system}.codex
        inputs.codex-switch.packages.${pkgs.system}.codex-switch
        (import ../modules/rtk.nix {
          inherit inputs;
          system = pkgs.stdenv.hostPlatform.system;
        })
      ];
    };
  desktop = [
    (import ./access/madeline.nix)
    (import ./access/extra-keys.nix)
    networkPolicy
    inputs.home-manager.nixosModules.home-manager
    inputs.sops-nix.nixosModules.sops
    inputs.tilingDesktop.nixosModules.default
    inputs.ashes-desktop-apps.nixosModules.default
    sshAgent
    (import ./access/module.nix)
    r640Env
    (
      { config, pkgs, ... }:
      {
        nix.settings.experimental-features = [
          "nix-command"
          "flakes"
        ];
        nixpkgs.config.allowUnfree = true;
        system.stateVersion = "26.05";
        services.openssh.enable = true;
        services.openssh.settings = {
          PasswordAuthentication = false;
          KbdInteractiveAuthentication = false;
          PermitRootLogin = "prohibit-password";
        };
        users.users.ash = {
          isNormalUser = true;
          description = "Ash";
          extraGroups = [
            "networkmanager"
            "wheel"
          ];
        };
        home-manager.useGlobalPkgs = true;
        home-manager.useUserPackages = true;
        home-manager.users.madeline.home.packages = [
          inputs.codex-nixpkgs.legacyPackages.${pkgs.system}.codex
          inputs.codex-switch.packages.${pkgs.system}.codex-switch
        ];
        home-manager.users.ash = {
          imports = [
            inputs.ashzsh.homeModules.default
            ../modules/fastfetch-arbor.nix
            inputs.tilingDesktop.homeModules.hyprland
            inputs.ashes-desktop-apps.homeModules.default
          ];
          home.stateVersion = "26.05";
          home.username = "ash";
          home.homeDirectory = "/home/ash";
          ashesDesktopApps = {
            enable = true;
            sets = [ "desktop.core" ];
          };
          programs.ssh = {
            enable = true;
            enableDefaultConfig = false;
            matchBlocks = config.arbor.environment.public.sshHosts;
          };
        };

        # The r640 machine identity is a narrowly scoped public grant.  The
        # matching private identity remains runtime-only on the source host.
        arbor.access.authorizedKeySets = [ "r640EvolverDeployer" ];
        users.users.ash.openssh.authorizedKeys.keys = (import ./access).r640EvolverDeployerKeys;
      }
    )
  ];
  server = [
    (import ./access/madeline.nix)
    (import ./access/extra-keys.nix)
    networkPolicy
    inputs.home-manager.nixosModules.home-manager
    {
      nix.settings.experimental-features = [
        "nix-command"
        "flakes"
      ];
      system.stateVersion = "26.05";
      services.openssh.enable = true;
      services.openssh.settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
        PermitRootLogin = "prohibit-password";
      };
      home-manager.useGlobalPkgs = true;
      home-manager.useUserPackages = true;
    }
  ];
  r640 = [
    (import ./access/module.nix)
    (import ./modules/github-runner.nix)
    {
      arbor.access.authorizedKeySets = [
        "operator"
        "deployment"
      ];
    }
    inputs.sops-nix.nixosModules.sops
    sshAgent
    { virtualisation.docker.enable = true; }
    r640Users
    r640Env
    vscodeRemoteModule
    serverTools
    (import ./machines/r640-0/storage.nix)
    (import ./machines/r640-0/management.nix)
  ];
  arborParticipant = [
    inputs.arbor-registry.nixosModules.default
    inputs.arbor-registry.nixosModules.service-contract
    (
      { lib, ... }:
      {
        cluster.registry.enable = true;
        cluster.registry.runtime = {
          enable = true;
          stateDirectory = "arbor-registry-canary-v1";
          transportStateDirectory = "arbor-registry-transport-canary-v1";
          bootstrapAuthoritiesFile = "/var/lib/arbor-registry-canary-v1/bootstrap-authorities.json";
          transportRealmId = "nix-arbor-live-v1";
          transportProtocolEpoch = 1;
          transportListen = [ ];
          transportBootstrapPeers = [ ];
        };

        # The pinned status probe exposes the socket token in its process arguments.
        systemd.services.arbor-runtime-status = {
          enable = false;
          wantedBy = lib.mkForce [ ];
        };
        systemd.timers.arbor-runtime-status = {
          enable = false;
          wantedBy = lib.mkForce [ ];
        };
      }
    )
  ];
  privateYggParticipant = [
    inputs.yggdrasil-private.nixosModules.default
    (
      { config, pkgs, ... }:
      {
        # The provider module stays dormant until it can consume runtime enrollment.
        _module.args = {
          hostName = config.networking.hostName;
          hostInventory.dendrites = [ "network/yggdrasil-private" ];
          site.networks.privateYggdrasil.networkManager = {
            enable = true;
            package = inputs.arbor-network-manager.packages.${pkgs.stdenv.hostPlatform.system}.default;
            socket = "/run/arbor/ygg-provider.sock";
          };
        };
      }
    )
  ];
  machines = inputs.arbor-manager.lib.mkMachines {
    inherit inputs;
    machinesPath = ./machines;
    extraModules = [ { time.timeZone = "America/Chicago"; } ];
    profiles = {
      inherit
        arborParticipant
        desktop
        privateYggParticipant
        server
        r640
        vscodeRemote
        ;
    };
  };
in
{
  perSystem = { pkgs, ... }: {
    packages.raspberry-evolver-image = import ./raspberry-evolver-image.nix {
      inherit pkgs;
      pi = self.nixosConfigurations.raspberry-evolver;
    };
  };
  flake.nixosConfigurations = machines.configurations // {
    raspberry-evolver = inputs.nixos-raspberrypi.lib.nixosSystem {
      nixpkgs = inputs.nixpkgs;
      trustCaches = false;
      specialArgs = {
        inherit inputs;
        machine = machines.machines.raspberry-evolver.machine;
        nixos-raspberrypi = inputs.nixos-raspberrypi;
      };
      modules = machines.machines.raspberry-evolver.modules ++ [
        inputs.nixos-raspberrypi.nixosModules.raspberry-pi-4.base
        inputs.nixos-raspberrypi.nixosModules.sd-image
      ];
    };
    # Temporary test-only output for the captured eVolver generation 10 baseline.
    # See docs/registry-canary.md for mandatory access and state preflight.
    eVolver-registry-canary = machines.configurations.eVolver.extendModules {
      modules = [
        ({ lib, pkgs, ... }: {
          users.users.madeline.openssh.authorizedKeys.keys = lib.mkForce [ ];
          home-manager.users.madeline = lib.mkForce {
            home.username = "madeline";
            home.homeDirectory = "/home/madeline";
            home.stateVersion = "26.05";
          };
          systemd.services.home-manager-madeline = {
            restartIfChanged = false;
            serviceConfig.ExecStart = lib.mkForce "${pkgs.coreutils}/bin/true";
          };
        })
      ];
    };
  };
}
