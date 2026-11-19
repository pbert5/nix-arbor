{ pkgs, ... }:
let
  release = "/var/lib/raspberry-evolver/thin-release";
  installThin = pkgs.writeShellScript "install-raspberry-evolver-thin" (
    builtins.readFile ./install-thin.sh
  );
  cleanRelease = pkgs.writeShellScript "clean-raspberry-evolver-thin-release" ''
    set -eu
    cd ${release}
    ${pkgs.coreutils}/bin/touch .installed
    ${pkgs.coreutils}/bin/sync -f .
    ${pkgs.coreutils}/bin/rm -f -- images.tar.gz evolver.bundle thin-images SHA256SUMS
  '';
  path = with pkgs; [
    bash
    coreutils
    diffutils
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
    unitConfig.ConditionPathIsDirectory = release;
    inherit path;
    serviceConfig = {
      Type = "oneshot";
      User = "ash";
      UMask = "0077";
      TimeoutStartSec = "15min";
      ExecStart = installThin;
      ExecStartPost = "+${cleanRelease}";
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
