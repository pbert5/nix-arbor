{
  user1 = {
    system = "x86_64-linux";
    home = {
      directory = "/home/user1";
      homeModule = "ash";
      stateVersion = "25.11";
      username = "user1";
    };
    nixos = {
      extraGroups = [
        "wheel"
        "networkmanager"
      ];
      shellPackage = "fish";
    };
    org = {
      flakeTarget.path = "/work/flake";
      home.sharedModules = [
        "shared/common"
        "shared/ssh"
        "shared/workstation"
      ];
    };
  };

  user2 = {
    system = "x86_64-linux";
    home = {
      directory = "/home/user2";
      homeModule = "madeline";
      stateVersion = "25.11";
      username = "user2";
    };
    nixos = {
      extraGroups = [
        "wheel"
        "networkmanager"
      ];
      shellPackage = "bashInteractive";
    };
    org = {
      flakeTarget.path = "/work/flake";
      home.sharedModules = [
        "shared/common"
        "shared/ssh"
        "shared/workstation"
      ];
    };
  };
}
