{
  pkgs,
  python3,
  tapelibPackage,
  ltfsOpen,
}:

pkgs.writeShellApplication {
  name = "backupper-runner";
  runtimeInputs = [
    pkgs.coreutils
    pkgs.findutils
    pkgs.fuse
    pkgs.fuse3
    pkgs.gnugrep
    pkgs.lsscsi
    pkgs.lsof
    pkgs.mtx
    pkgs.sg3_utils
    pkgs.sqlite
    pkgs.systemd
    pkgs.util-linux
    ltfsOpen
  ];
  text = ''
    export PYTHONPATH="${tapelibPackage}/${python3.sitePackages}:''${PYTHONPATH:-}"
    exec ${python3}/bin/python ${./backupper-runner.py} "$@"
  '';
}
