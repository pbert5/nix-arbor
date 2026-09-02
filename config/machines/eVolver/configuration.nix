{
  config,
  inputs,
  lib,
  ...
}:
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
    # The retained live configuration is one schema revision newer than the
    # currently pinned package. Keep the existing state and let Syncthing
    # perform its supported compatibility read during the migration.
    extraFlags = [ "--allow-newer-config" ];
  };
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };

  # Use compressed RAM as the first pressure tier, with the declarative
  # swapfile in hardware-configuration.nix as an emergency buffer.  25% is
  # intentionally conservative for this 8 GiB-class host.
  zramSwap = {
    enable = true;
    memoryPercent = 25;
    priority = 100;
  };
  systemd.oomd = {
    enable = true;
    enableUserSlices = true;
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

  # Preserve the access path and controller during pressure without making
  # every process unkillable.  Ordinary user workloads remain reclaimable.
  systemd.services.sshd.serviceConfig = {
    OOMScoreAdjust = -900;
    ManagedOOMPreference = "avoid";
  };
  systemd.services.tailscaled.serviceConfig = {
    OOMScoreAdjust = -700;
    ManagedOOMPreference = "avoid";
  };
  systemd.services.evolver-controller.serviceConfig = {
    OOMScoreAdjust = -500;
    ManagedOOMPreference = "avoid";
  };
  systemd.services.evolver-hardware.serviceConfig = {
    OOMScoreAdjust = -400;
    ManagedOOMPreference = "avoid";
  };

  assertions = [
    {
      assertion = lib.any (
        key:
        lib.hasPrefix "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINa/sAnukQD4gdu8zZ/m3+SavLJNrtjJcC4swgebGnZN" key
      ) config.users.users.ash.openssh.authorizedKeys.keys;
      message = "eVolver Ash must authorize the r640 machine public SSH key";
    }
    {
      assertion = lib.any (
        key:
        lib.hasPrefix "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINa/sAnukQD4gdu8zZ/m3+SavLJNrtjJcC4swgebGnZN" key
      ) config.users.users.root.openssh.authorizedKeys.keys;
      message = "eVolver root must authorize the r640 machine public SSH key";
    }
    {
      assertion = config.zramSwap.enable && config.zramSwap.memoryPercent == 25;
      message = "eVolver must retain its conservative zram pressure tier";
    }
    {
      assertion = lib.any (
        swap: swap.device == "/var/lib/swapfile" && swap.size == 8192
      ) config.swapDevices;
      message = "eVolver must retain its 8 GiB emergency swapfile";
    }
    {
      assertion = config.systemd.services.sshd.serviceConfig.OOMScoreAdjust == -900;
      message = "eVolver SSH must retain its OOM survival preference";
    }
    {
      assertion = config.systemd.services.tailscaled.serviceConfig.OOMScoreAdjust == -700;
      message = "eVolver Tailscale must retain its OOM survival preference";
    }
    {
      assertion = config.systemd.services.evolver-controller.serviceConfig.OOMScoreAdjust == -500;
      message = "eVolver controller must retain its OOM survival preference";
    }
    {
      assertion = config.systemd.services.evolver-hardware.serviceConfig.OOMScoreAdjust == -400;
      message = "eVolver hardware service must retain its OOM survival preference";
    }
  ];

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
