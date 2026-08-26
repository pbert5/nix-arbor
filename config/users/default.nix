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
        builtins.length config.users.users.ash.openssh.authorizedKeys.keys >= 9
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
    openssh.authorizedKeys.keys = [
      "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBPnLRavaTbytLjtdaM/SXSLpdg3Z0MUvpYEoyKDcDk7GO/tbeIKQxz6kysk2G/UiO7x8Ulhe1bbkgBkwi+8TR5Y= ash-iphone"
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK37SqGag+fd939XSZT+ytV3/KOzI6K9N/sDq3nye27O ash@windows-machine"
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKKJ8mhwR1PeloNNp5vzroZaQ4ga0x1TLi2f/2DX1lPs admin@toptoodle"
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKRnn0GgKyiHU+v4oBbOp40e3hpEZOZ/iKW9Jhtpaker bertinert"
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDE3UBc1SScbr08iKGk3vRBqDjHekPfwioFsHilyYriurgxzrnFAHfMPIDKp0mDFBAYRJlClDPqstGGiqzHG+ZX02qDVbVT98le9DDA9LPMsRfCYcQVm+lJ4g22ILcsA1fa60wVq0XQBnoqCfjQzhFDI1jkDxVl6Z7B6sC3OUZnkv+OXYY/xWpoHEHEF0zv+7sDg/mAFSbVY1UiOQVwTPymRPZCAMDxNrpVaqZNQ4mHmk/TMqN/XCA8Qg7Ehj6n7K+XUsfu/GS+MCzCcQvQ7ChLqLDbwXFIIvoaX/Rf6xnD0aABcMwvMs4hfSQ5s9wAeM/ngC6BmORpKALR32EFWQZbYBh6Bt5QlXhkzv5oNXUzMRrRa3yyHpOYDD8cpKNWOM88vociki63lOssKFiG+nSDAmCCg4z0yLDa481Di0Tk1fDBGmVeUwwsYJldQRbtmk4ksOJyrS23RQHSEouqTwC0/bWDj5iKUZ7uF8jtNrfJY4QhthkUkYKSgvW5dQAxlB8= root@truenas"
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCujnt9Jf4FLMXwKzBc7vHXMrmtg+9dUYtxO/PoSE3GQoFsHmlx4seSToddx3GKykxw4NXoR2XjvTCCQUZ5Q3BdiTJO5LeOoltUzBLJw/SN1zD1dXTalTlaIV9HKYyuyZkYeKDgOOopjv5CJgXzAymE2lwhL35FkYlCLQRxhkuAzI6J8ciC51uRQcv6QVoRQtB3PRelQDrxbussqOZhen2mASLUswVPFa+P2GMrd0zyzmR5YixikcGMDdTuYtqIJfxgWxDu2QpP36m8N55C+DBpSLmjMtTF5AW8i29ghQ6QOhPuO8mtoYjaoMjzgnyVpDBg9p/bZ0SWCESC6ku4ioTqTyZBzr3PT8/pFp9/8bJ1elHXfTlG6haEiQE7shc+lGT/PL2j1p6iwlTgWuLrOebyZzouTLT8mofAc08uL7sspvrBU8a0OP+tX6+WXzE3eLQw3fmPLdJ1m6/ey+qQrJ4/j1hnGVl4jlv4NTOLXSqZ/Mpc7oPbDKLwD2y6fAMOVmevqzjGDZAbAKaHa0SQc6dFvc2VwVt3kEAuHQJmE3heEL2Bj4BZzig9ZobdtQu96cIsD6rR9FlA+bnDPjMfPqZoqawTPWIJ96b90Iz0CyxAWX9DXRfDfWIq9C1I6ZmYNI2mReWzQRZhAcJw7FPSTd0ADoIIIe46+yy1uyJgxLnYdQ== ash@linux 2026-04-19"
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCvNI0F9iH9Dhk0iCyvWrL8NGG4wd9GvEkbll3CZq/OKorynB8Dfov/rKfj4wTPiNdgdbUuH2gmB68MQjkNQlFuSmOgAefovfNK5wTUHQ7lWKYLfnWoZVSVT4KrLAusq6nvQDOJXCcEuR083IjvZgM/uVkomA/5nojcMRK9Vt9Xx97kmPWDMB8E1dS/sFSS1UWmyqJaABILKzT8ZNsaEanr5dbF2PY6YdjoiJqjjD3OFz6l1K0Cp652ZHhyo+/wd+zAUMuVttDDH2pZxaVRiofvy6z3QzT3YpYdAEqgx+dRF0tq+hwWfbU87al8MRCRYM/aiSTgHxLrJJTnS60OEJiC30HxPIHYqK54JRowvgZes0Yj/BfjkwvK0Um7tp7AF2xipCth/FGPDGL7wqUWujyP+s9sIeJO2o/9fqLKrox7HllWiUT1ZPCh0exKdiV0mqt/r3g+VCDTasrHvF1+t+7Caf61UqLddKzZJUfyqLMS1Oy5OxXK1O0pK3bm8K6U3+NYmtJ1v4hvgMCQbnSAbB1ZojMqOO8MaW56dNlm0x/SBOugpY3xTuMpImwo59/cA4Eaq+oZqZquda4bAlzKp0jh/aHrlTMClutLk/dv4i7IxIEsEKX1h8rmMYR6qy3YJWyuMV6ilj8lSouozHlXc5hfjWylzj6CxZ4p237Hsq8eFw== root@R730-0"
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCwheo5UX9Ds48CxJLa0Spe4ms5ldW9nDVEBG9ir/2ONw1u/SIhCxAo1ONc1UbE3Xft3w0tVKP7sY/voHqB3q0sG9C+12cRN1KjNP3GCKZSRn/US5l2Ji79yqAPqYRnQp3d7jR6YhUafq6N0NIryFpeKwATTJfyQVBhJHGlLgihuxei7bjP43t4ANpDmZppIRo+qtSMfS1vvTTdNUKQbZI4xvmM8G5PFBEIo7Nfe6HbP1xRMNRU8y5hxB8fLHzUqWKT9DIaVaQ9C7BTxX4yniP/h8WTMYzgcEVEK2ifQ3Qz80lM0ES/kMbD/0KskSE8wNj1R3jbJK/P8Kz22G4H6FU9YT+KW2XHhWqX4I3MbC8LfV5OYklhcAuOP/LmDo+EIQGYyuBWcCBvX70bOrlSq893PrEvakK5Wh/UqSFwgNF1dn23yEFHkM8njF3nrPg7USNzS5m7Ch3JBobUVRqnYhLwEtKFL60cdi1nA/JThFCq+bnLadNhorS8Oh0NY/4HuXprLfTvqIgImPWO//MS8Wz52pi3f6ogmOtFFBmcL2LW6RcRKfFPWkIVK3qhaI4CXGJECVc7MIfAosgk9PyL/i4Dx9VTcMVA6GJWDMVMNn4gzMTxyI8Q17USUZuXFYtFKdYsxiXfVPvCsLuPvQ4xIpPX3pASm2gHBy0b+tBgnNfUsw== phsilbert@gmail.com"
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDD72jIDEuYHCZXxxFvYHt3IcoQRGxBoRGCIy5kiaYcKkpLC8Noh6OZg0rHNbmfRao0DFzdCuVMmTAy+p7NV4w/CGLosytjSARQ91xRKdPoJVO4j5WMd+dgJREr3sqGflI3HVuQmqsFTKKBs3P4CjkyPE0yBaHkU0FVZf5ww+y0xkO1RySEDN3nTLtI6353zJa6D4WQokzL7W9yoB9mjzL092xqO3fr3DVKrnh5HFKlKOq2hbFVxo6hvCMCfJCuvkTpO3QRvlt/IHClqBUf8UGDT7aY0Dv3WhLCN5EbMCO1zuS1wyxq2wNpBhFpxRtbusxkaCOKAdrVyAAXcky51b8GrkBpHn37ybmYHEnpgXMA2SClKvfwUP3ObLdV7zqGo0kGFoC4HJiZiMx7oroer+smmx6zW1fFL6LuBq9gocXM6pp9Dsf/3jA3GCy0d/yyMNbIHfpYyUxy0WHTL8XjJm9J2K308lkQeikswtcikzAkoCUMhR08fTDuoDo5eORe1OGVd7+Y4F8iGV5rzDYlhmTdqj0/rPfxVLu2rbaOVKBUyQgPPkPcYHzvJXyV/BdQjCGcm2+gYR9HAPkWJjqR7q88gNa0OgyJWZXHWP3hpKQ4Mt9k23Veh8RGMx6ixYuHFKuUNovhj3m0GBkBFp4mYWos3J4iVuq02jamB7JIQJZmsw== r640-0"
    ];
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
