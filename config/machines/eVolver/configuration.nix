{ lib, ... }:
{
  imports = [
    ../../access/module.nix
    ../../users/default.nix
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
  ];
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };

  # eVolver is an always-available workstation.  Retain this host behaviour
  # while leaving desktop and application selection to shared profiles.
  services.displayManager.gdm.autoSuspend = false;
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
