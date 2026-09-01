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
    "r640EvolverDeployer"
  ];
  users.users.root.openssh.authorizedKeys.keys = (import ../../access).r640EvolverDeployerKeys;
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
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
