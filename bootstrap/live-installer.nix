{
  lib,
  pkgs,
  modulesPath,
  ...
}:
let
  leaderKeysDir = ../inventory/keys/leaders;
  leaderKeyFiles = builtins.map (name: leaderKeysDir + "/${name}") (
    builtins.attrNames (lib.filterAttrs (_: type: type == "regular") (builtins.readDir leaderKeysDir))
  );
  leaderAuthorizedKeys = lib.concatMap (
    path: builtins.filter (line: line != "") (lib.splitString "\n" (builtins.readFile path))
  ) leaderKeyFiles;
in
{
  imports = [
    (modulesPath + "/installer/cd-dvd/installation-cd-minimal.nix")
  ];

  networking.hostName = lib.mkDefault "nbootstrap-live";
  environment.etc."clusterctl-install-target".text = "nbootstrap-live-v1\n";

  # The live image has no root ZFS pool to import; keep 26.05 evaluation quiet
  # and avoid any forced import if ZFS tooling probes attached disks.
  boot.zfs.forceImportRoot = false;

  services.openssh = {
    enable = true;
    settings = {
      KbdInteractiveAuthentication = false;
      PasswordAuthentication = false;
      PermitRootLogin = "yes";
    };
  };

  users.users.root.openssh.authorizedKeys.keys = leaderAuthorizedKeys;

  environment.systemPackages = with pkgs; [
    gitMinimal
    jq
    yggdrasil
  ];

  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];

  system.nixos.tags = [ "nbootstrap-live" ];
}
