{
  dev-machine = {
    endpointHost = "dev-machine";
    listen = true;
    peers = [
      "r640-0"
      "desktoptoodle"
    ];
    aliases = [ "dev-machine-ygg" ];
  };

  compute-worker = {
    endpointHost = "compute-worker";
    listen = false;
    peers = [ "dev-machine" ];
    aliases = [ "compute-worker-ygg" ];
  };
}
