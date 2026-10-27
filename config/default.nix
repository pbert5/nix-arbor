{ inputs, ... }:
let
  networkPolicy = import ./networks.nix;
  sshAgent = import ./modules/ssh-agent.nix;
  r640Users = import ./users;
  r640Env = import ./env.nix;
  r640Sops = import ./sops.nix;
  vscodeRemoteModule = import ./modules/vscode-remote.nix;
  vscodeRemote = [ vscodeRemoteModule ];
  registryServiceContract =
    if builtins.hasAttr "service-contract" inputs.arbor-registry.nixosModules then
      inputs.arbor-registry.nixosModules.service-contract
    else
      # Compatibility for locks predating the exported module; input wins as
      # soon as the Registry input publishes the service-contract export.
      import ../packages/arbor-registry/modules/service-contract.nix;
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
        pkgs.codex
        inputs.codex-switch.packages.${pkgs.system}.codex-switch
        rtk
      ];
    };
  desktop = [
    networkPolicy
    inputs.home-manager.nixosModules.home-manager
    inputs.sops-nix.nixosModules.sops
    inputs.tilingDesktop.nixosModules.default
    inputs.ashes-desktop-apps.nixosModules.default
    sshAgent
    (import ./access/module.nix)
    r640Env
    (
      { config, ... }:
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
        home-manager.users.ash = {
          imports = [
            inputs.ashzsh.homeModules.default
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

        # The r640 machine identity is a narrowly scoped public grant. The
        # matching private identity remains runtime-only on the source host.
        arbor.access.authorizedKeySets = [ "r640EvolverDeployer" ];
        users.users.ash.openssh.authorizedKeys.keys = (import ./access).r640EvolverDeployerKeys;
      }
    )
  ];
  server = [
    networkPolicy
    inputs.home-manager.nixosModules.home-manager
    r640Env
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
  # Operator tooling is deliberately a reusable profile. Participants do not
  # receive the Manager merely by joining the Arbor runtime.
  arborOperator = [
    (
      { inputs, pkgs, ... }:
      {
        environment.systemPackages = [
          inputs.arbor-manager.packages.${pkgs.system}.arbor-manager
        ];
      }
    )
  ];
  r640 = [
    (import ./access/module.nix)
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
    r640Sops
    vscodeRemoteModule
    serverTools
    (import ./machines/r640-0/storage.nix)
    (import ./machines/r640-0/management.nix)
  ]
  ++ arborOperator;
  arborParticipant = [
    inputs.arbor-registry.nixosModules.default
    registryServiceContract
    {
      # This is a public policy/status boundary only. Runtime credentials,
      # initialization, and unseal remain explicit operator actions.
      cluster.registry.enable = true;
      cluster.registry.runtime.enable = true;
    }
  ];
  privateYggParticipant = [
    inputs.yggdrasil-private.nixosModules.default
    (
      {
        config,
        inputs,
        pkgs,
        ...
      }:
      {
        # This is the special Arbor Network Manager mode. The private-Ygg
        # module owns transport, pinning, firewall separation, and the
        # provider service; accepted node records are supplied separately
        # when this host is enrolled.
        _module.args = {
          hostName = config.networking.hostName;
          hostInventory.dendrites = [ "network/yggdrasil-private" ];
          site.networks.privateYggdrasil.networkManager = {
            enable = true;
            package = inputs.arbor-network-manager.packages.${pkgs.system}.default;
            socket = "/run/arbor/ygg-provider.sock";
          };
        };
      }
    )
  ];
  machines = inputs.arbor-manager.lib.mkMachines {
    inherit inputs;
    machinesPath = ./machines;
    profiles = {
      inherit
        arborOperator
        arborParticipant
        privateYggParticipant
        desktop
        server
        r640
        vscodeRemote
        ;
    };
  };
in
{
  flake.nixosConfigurations = machines.configurations;
}
