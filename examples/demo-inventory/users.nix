{
  user1 = {
    roles = [ "workstation" ];
    system = "x86_64-linux";
    home = {
      directory = "/home/user1";
      homeModule = "user1";
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
    org.flakeTarget.path = "/work/flake";
  };

  user2 = {
    roles = [ "workstation" ];
    system = "x86_64-linux";
    home = {
      directory = "/home/user2";
      homeModule = "user2";
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
    org.flakeTarget.path = "/work/flake";
  };
}
