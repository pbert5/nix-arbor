{
  ash = {
    roles = [ "workstation" ];
    system = "x86_64-linux";
    home = {
      directory = "/home/example";
      homeModule = "ash";
      stateVersion = "25.11";
      username = "ash";
    };
    nixos = {
      
      extraGroups = [
        "docker"
        "wheel"
        "networkmanager"
      ];
      hashedPassword = null;
      shellPackage = "fish";
    };
    org = {
      flakeTarget.path = "/work/flake";
    };
  };

  madeline = {
    roles = [ "workstation" ];
    system = "x86_64-linux";
    home = {
      directory = "/home/example";
      homeModule = "madeline";
      stateVersion = "25.11";
      username = "madeline";
    };
    nixos = {
      extraGroups = [
        "docker"
        "wheel"
        "networkmanager"
      ];
      shellPackage = "bashInteractive";
    };
    org = {
      flakeTarget.path = "/work/flake";
    };
  };
}
