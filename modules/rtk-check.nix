{
  config,
  inputs,
  pkgs,
  system,
}:
let
  rtkFor = system: inputs.rtk-nixpkgs.legacyPackages.${system}.rtk;
  expected = rtkFor system;
  selected = packages: builtins.filter (p: (p.pname or "") == "rtk") packages;
  usesExpected =
    expectedRtk: packages:
    let
      matches = selected packages;
    in
    builtins.length matches == 1 && (builtins.head matches).drvPath == expectedRtk.drvPath;
  machines = config.flake.nixosConfigurations;
  serverUsesExpected =
    machine:
    usesExpected (rtkFor machine.pkgs.stdenv.hostPlatform.system) machine.config.environment.systemPackages;
in
assert expected.version == "0.50.0";
assert expected.meta.license.free;
assert !(builtins.tryEval pkgs.rtk.drvPath).success;
assert usesExpected expected config.flake.devShells.${system}.default.nativeBuildInputs;
assert serverUsesExpected machines.eVolver;
assert serverUsesExpected machines.r640-0;
pkgs.runCommand "nix-arbor-free-rtk" { } ''touch "$out"''
