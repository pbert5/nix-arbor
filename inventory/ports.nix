{
  selfAssemblingClusterCache = {
    allowedCidrs = [
      "127.0.0.1/32"
      "100.64.0.0/10"
    ];
    bind = "127.0.0.1";
    hosts = [
      "127.0.0.1"
      "localhost"
    ];
    port = 5000;
  };

  selfAssemblingClusterManifests = {
    allowedCidrs = [
      "127.0.0.1/32"
      "100.64.0.0/10"
    ];
    bind = "127.0.0.1";
    hosts = [
      "127.0.0.1"
      "localhost"
    ];
    port = 8080;
  };

  tapeLibraryFossilsafe = {
    allowedCidrs = [
      "127.0.0.1/32"
      "100.64.0.0/10"
    ];
    bind = "127.0.0.1";
    hosts = [
      "127.0.0.1"
      "localhost"
    ];
    port = 5001;
  };

  tapeLibraryYatm = {
    allowedCidrs = [
      "127.0.0.1/32"
      "100.64.0.0/10"
    ];
    bind = "127.0.0.1";
    hosts = [
      "127.0.0.1"
      "localhost"
    ];
    port = 8081;
  };

  tapeLibraryYatmDebug = {
    allowedCidrs = [
      "127.0.0.1/32"
      "100.64.0.0/10"
    ];
    bind = "127.0.0.1";
    hosts = [
      "127.0.0.1"
      "localhost"
    ];
    port = 8082;
  };

  # SeaweedFS hot pool — all ports are private-overlay-only.
  # Bound to the Yggdrasil interface address, not to 0.0.0.0.
  seaweedfsMaster = {
    allowedCidrs = [ ]; # populated by seaweedfs-hot firewall leaf from Ygg peers
    bind = "ygg0"; # symbolic; resolved to the Ygg address at module time
    port = 9333;
  };

  seaweedfsVolume = {
    allowedCidrs = [ ];
    bind = "ygg0";
    port = 8090;
  };

  seaweedfsFiler = {
    allowedCidrs = [ ];
    bind = "ygg0";
    port = 8888;
  };

  seaweedfsS3 = {
    allowedCidrs = [ ];
    bind = "ygg0";
    port = 8333;
  };

  # Radicle P2P node — private overlay only.
  radicleNode = {
    allowedCidrs = [ ];
    bind = "ygg0";
    port = 8776;
  };
}
