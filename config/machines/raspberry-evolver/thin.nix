{ pkgs, ... }:
let
  release = "/var/lib/raspberry-evolver/thin-release";
  installThin = pkgs.writeShellScript "install-raspberry-evolver-thin" (
    builtins.readFile ./install-thin.sh
  );
  path = with pkgs; [
    bash
    coreutils
    docker
    gnugrep
    gnused
    git
    gzip
    openssl
    python3
    util-linux
  ];
in
{
  systemd.services.raspberry-evolver-install-thin = {
    description = "Import the bundled Simple Evolver release";
    requires = [ "docker.service" ];
    after = [ "docker.service" ];
    unitConfig.ConditionPathExists = "${release}/SHA256SUMS";
    inherit path;
    serviceConfig = {
      Type = "oneshot";
      User = "ash";
      UMask = "0077";
      TimeoutStartSec = "15min";
      ExecStart = installThin;
      ExecStartPost = "+${pkgs.coreutils}/bin/rm -- ${release}/SHA256SUMS ${release}/images.tar.gz ${release}/evolver.bundle ${release}/thin-images";
    };
  };

  systemd.services.raspberry-evolver-thin = {
    description = "Start Simple Evolver thin from prepared images";
    wantedBy = [ "multi-user.target" ];
    requires = [
      "docker.service"
      "raspberry-evolver-install-thin.service"
    ];
    after = [
      "docker.service"
      "raspberry-evolver-install-thin.service"
    ];
    unitConfig.ConditionPathExists = "/home/ash/evolver/tools/localctl";
    inherit path;
    serviceConfig = {
      Type = "oneshot";
      User = "ash";
      WorkingDirectory = "/home/ash/evolver";
      TimeoutStartSec = "5min";
      ExecStart = "${pkgs.bash}/bin/bash /home/ash/evolver/tools/localctl thin boot";
    };
  };
}
