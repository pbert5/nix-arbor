{
  dev-machine = {
    exported = false;
    system = "x86_64-linux";
    roles = [ "workstation" ];
    networks = [
      "privateYggdrasil"
      "tailscale"
    ];
    publicYggdrasil = false;
    dendrites = [
      "system/cluster-identity"
      "media/game-library"
    ];
    fruits = [ ];
    users = [
      "ash"
      "madeline"
    ];
    facts = { };
    org.clusterIdentity = {
      role = "follower";
      services = {
        ssh.enableLiveKnownHosts = true;
        yggdrasil.enableLiveIdentity = true;
        radicle.enableLiveIdentity = false;
        gitAnnex.enableLiveIdentity = false;
      };
    };
    hardwareModules = [ ];
    overrides = [ "dev-machine" ];
  };

  compute-worker = {
    exported = false;
    system = "x86_64-linux";
    roles = [ "compute-worker" ];
    networks = [ "privateYggdrasil" ];
    publicYggdrasil = false;
    dendrites = [ ];
    fruits = [ ];
    users = [ ];
    facts = { };
    org = { };
    overrides = [ ];
  };
}
