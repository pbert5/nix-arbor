let
  access = import ../access;
in
{
  config,
  inputs,
  lib,
  pkgs,
  ...
}:
{
  assertions = [
    {
      assertion = config.users.users.ash.uid == 1000;
      message = "The ash identity must use UID 1000.";
    }
    {
      assertion = config.users.users.madeline.uid == 1001;
      message = "The madeline identity must use UID 1001.";
    }
    {
      assertion = config.users.groups.home-share.gid == 993;
      message = "The home-share group must use GID 993.";
    }
    {
      assertion =
        builtins.length config.users.users.ash.openssh.authorizedKeys.keys
        >= builtins.length access.operatorKeys
        &&
          builtins.length (
            builtins.filter (
              key:
              lib.hasPrefix "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAbYbxGzSboO3llrd28uOHpybxTLrbDZN/QmY0crRxU0" key
              || lib.hasPrefix "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINa/sAnukQD4gdu8zZ/m3+SavLJNrtjJcC4swgebGnZN" key
            ) config.users.users.ash.openssh.authorizedKeys.keys
          ) >= 1
        && lib.all (
          key: lib.hasPrefix "ssh-" key || lib.hasPrefix "ecdsa-" key
        ) config.users.users.ash.openssh.authorizedKeys.keys;
      message = "Ash must retain the recovered public SSH key set without private material.";
    }
  ];
  programs.zsh.enable = true;
  users.groups.home-share.gid = 993;
  users.users.ash = {
    uid = 1000;
    isNormalUser = true;
    description = "Ash";
    shell = pkgs.zsh;
    extraGroups = [
      "wheel"
      "docker"
      "networkmanager"
      "dialout"
      "home-share"
    ];
    linger = true;
    # Public fallback keys only; private keys remain on operator devices.
    openssh.authorizedKeys.keys = lib.concatMap (
      set: access."${set}Keys"
    ) config.arbor.access.authorizedKeySets;
    hashedPasswordFile = lib.mkIf config.arbor.environment.secrets.enable config.sops.secrets.ash-password.path;
  };
  users.users.madeline = {
    uid = 1001;
    isNormalUser = true;
    description = "Madeline";
    shell = pkgs.zsh;
    extraGroups = [
      "wheel"
      "docker"
      "networkmanager"
      "dialout"
      "home-share"
    ];
    openssh.authorizedKeys.keys = [ ];
    hashedPasswordFile = lib.mkIf config.arbor.environment.secrets.enable config.sops.secrets.madeline-password.path;
  };
  home-manager.users.ash = {
    imports = [ inputs.ashzsh.homeModules.default ];
    home.username = "ash";
    home.homeDirectory = "/home/ash";
    home.stateVersion = "26.05";
    programs.git.enable = true;
    programs.btop = {
      enable = true;
      settings = {
        # ZFS mounts are not fstab entries; explicitly show the mounted pool
        # filesystem without listing its underlying devices or datasets.
        use_fstab = false;
        only_physical = false;
        zfs_hide_datasets = true;
        disks_filter = "/ /mypool";
      };
    };
    programs.git.settings = {
      user = {
        name = "ash-r640-0";
        email = "phsilbert@gmail.com";
      };
      # Keep Git's configuration fully Home Manager-owned.  The empty helper
      # first clears any lower-priority helper, matching `gh auth setup-git`,
      # and the shell helper asks gh for the active user's token at runtime.
      credential = {
        "https://github.com".helper = [
          ""
          "!${lib.getExe pkgs.gh} auth git-credential"
        ];
        "https://gist.github.com".helper = [
          ""
          "!${lib.getExe pkgs.gh} auth git-credential"
        ];
      };
    };
    programs.ssh = {
      enable = true;
      enableDefaultConfig = false;
      matchBlocks = config.arbor.environment.public.sshHosts;
    };
  };
  home-manager.users.madeline = {
    home.username = "madeline";
    home.homeDirectory = "/home/madeline";
    home.stateVersion = "26.05";
    programs.ssh = {
      enable = true;
      enableDefaultConfig = false;
      matchBlocks = config.arbor.environment.public.sshHosts;
    };
  };
}
