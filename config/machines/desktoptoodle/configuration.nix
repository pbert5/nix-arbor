{ lib, ... }:
{
  imports = [
    ../../access/module.nix
    ../../users/default.nix
  ];

  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 20;
  boot.loader.efi.canTouchEfiVariables = lib.mkDefault true;

  # Preserve the public/bootstrap SSH path independently of Arbor and Yggdrasil
  # convergence.  This host intentionally receives the operator grant only.
  arbor.access.authorizedKeySets = [ "operator" ];
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };
}
