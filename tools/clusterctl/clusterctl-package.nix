{
  age,
  coreutils,
  git,
  nix,
  openssh,
  python3,
  writeShellApplication,
}:

writeShellApplication {
  name = "clusterctl";
  runtimeInputs = [
    age
    coreutils
    git
    nix
    openssh
    python3
  ];
  text = ''
    export PYTHONPATH=${./.}
    exec ${python3}/bin/python -m clusterctl.main "$@"
  '';
}
