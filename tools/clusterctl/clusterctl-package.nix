{
  age,
  coreutils,
  curl,
  git,
  kubo,
  lib,
  navi,
  nix,
  nixos-anywhere,
  openssh,
  python3,
  sops,
  symlinkJoin,
  writeShellApplication,
  defaultFlake ? ".",
}:

let
  runtimeInputs = [
    age
    coreutils
    curl
    git
    kubo
    navi
    nix
    nixos-anywhere
    openssh
    python3
    sops
  ];
  mkCommand =
    name: mode:
    writeShellApplication {
      inherit name runtimeInputs;
      text = ''
        export CLUSTERCTL_EXECUTABLE="$0"
        export CLUSTERCTL_MODE=${lib.escapeShellArg mode}
        if [ -z "''${CLUSTERCTL_FLAKE+x}" ]; then
          export CLUSTERCTL_FLAKE=${lib.escapeShellArg defaultFlake}
        fi
        export PYTHONPATH=${./.}
        if [ "$#" -eq 0 ] && [ "$CLUSTERCTL_MODE" = operate ]; then
          exec navi --tag-rules clusterctl
        fi
        exec ${python3}/bin/python -m clusterctl.main "$@"
      '';
    };
in
symlinkJoin {
  name = "clusterctl";
  paths = [
    (mkCommand "clusterctl" "operate")
    (mkCommand "clusterchk" "check")
    (mkCommand "clusterplan" "plan")
  ];
}
