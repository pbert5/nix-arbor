{ pkgs }:

pkgs.runCommand "cluster-identity-registry-v1" {
  nativeBuildInputs = [
    pkgs.git
    pkgs.openssh
    pkgs.python3
  ];
} ''
  export HOME="$TMPDIR/home"
  export PYTHONPATH=${../tools/clusterctl}
  mkdir -p "$HOME"
  ${pkgs.python3}/bin/python -m unittest discover \
    -s ${../tools/clusterctl/tests} \
    -p 'test_*.py' \
    -v
  touch "$out"
''
