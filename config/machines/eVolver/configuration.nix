{ inputs, lib, ... }:
{
  imports = [
    ../../access/module.nix
    ../../env.nix
    ../../users/default.nix
    inputs.sops-nix.nixosModules.sops
  ];

  # Preserve the host's UEFI boot policy without importing its former
  # workstation application stack.
  boot.loader.grub.enable = lib.mkForce false;
  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 10;
  boot.loader.efi.canTouchEfiVariables = lib.mkDefault true;

  # The public operator and deployment grants are applied to the managed ash
  # account by config/users; no private deployment material is evaluated.
  arbor.access.authorizedKeySets = [
    "operator"
    "deployment"
    "r640EvolverDeployer"
  ];
  users.users.root.openssh.authorizedKeys.keys = (import ../../access).r640EvolverDeployerKeys;
  networking.networkmanager.enable = true;
  virtualisation.docker.enable = true;
  services.tailscale.enable = true;
  services.syncthing = {
    enable = true;
    user = "ash";
    dataDir = "/home/ash/.config/syncthing";
    configDir = "/home/ash/.config/syncthing";
    guiAddress = "127.0.0.1:8384";
  };
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };

  # Keep the existing controller release and state roots intact across
  # rebuilds. The release is maintained outside this flake; these units make
  # its lifecycle declarative without importing application secrets or data.
  systemd.services.evolver-hardware = {
    description = "eVOLVER read-only hardware service";
    wantedBy = [ "multi-user.target" ];
    wants = [ "network-online.target" ];
    after = [ "network-online.target" ];
    serviceConfig = {
      ExecStart = "/opt/evolver-controller/releases/0.2.0-4217b36-hardware-sync2/bin/evolver-hardware --state-root /var/lib/evolver-controller";
      Restart = "on-failure";
      RestartSec = 5;
      StateDirectory = "evolver-controller";
      StateDirectoryMode = "0750";
      UMask = "0077";
      SupplementaryGroups = [ "dialout" ];
      NoNewPrivileges = true;
    };
  };
  systemd.services.evolver-controller = {
    description = "eVOLVER edge controller";
    wantedBy = [ "multi-user.target" ];
    wants = [
      "network-online.target"
      "evolver-hardware.service"
    ];
    after = [
      "network-online.target"
      "evolver-hardware.service"
    ];
    serviceConfig = {
      ExecStart = "/opt/evolver-controller/releases/0.2.0-4217b36-hardware-sync2/bin/evolver-controller --state-root /var/lib/evolver-controller";
      Restart = "on-failure";
      RestartSec = 5;
      StateDirectory = "evolver-controller";
      StateDirectoryMode = "0750";
      UMask = "0077";
      NoNewPrivileges = true;
    };
  };

  # INTENTIONALLY HEADLESS: eVolver is an always-available server host.
  systemd.sleep.settings.Sleep = {
    AllowSuspend = false;
    AllowHibernation = false;
    AllowSuspendThenHibernate = false;
    AllowHybridSleep = false;
  };
  systemd.targets = {
    sleep.enable = false;
    suspend.enable = false;
    hibernate.enable = false;
    hybrid-sleep.enable = false;
  };
}
