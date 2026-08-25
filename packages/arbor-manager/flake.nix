{
  description = "Arbor Manager: reusable static machine inventory to NixOS assembly";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      managerLib = import ./lib { inherit (nixpkgs) lib; };
      snapshot = import ./lib/snapshot.nix { inherit (nixpkgs) lib; };
      lib = managerLib // {
        inherit snapshot;
      };
    in
    {
      inherit lib;
      formatter = forAllSystems (system: (import nixpkgs { inherit system; }).nixfmt-tree);
      checks = forAllSystems (system: {
        fixtures =
          let
            fixtureInputs = { inherit nixpkgs; };
            assembled = lib.mkMachines {
              inputs = fixtureInputs;
              machinesPath = ./tests/fixtures;
              profiles.server = [ ];
            };
            valid = lib.validateMachine "fixture" {
              system = "x86_64-linux";
              profiles = [ "server" ];
            };
            invalid = builtins.tryEval (lib.validateMachine "broken" { system = "i686-linux"; });
            pure = lib.mkMachines {
              inputs = fixtureInputs;
              sources = [
                {
                  name = "pure";
                  record = {
                    system = "x86_64-linux";
                    profiles = [ ];
                    hostname = "pure-host";
                    cluster = {
                      relationshipData = [ "parent-a" ];
                    };
                  };
                  provenance = {
                    kind = "test";
                    source = "pure";
                  };
                  precedence = 7;
                }
              ];
            };
            snapshot = lib.mkMachines {
              inputs = fixtureInputs;
              sources = lib.registrySnapshot {
                digest = "sha256:test-snapshot";
                machines = {
                  snapshot = {
                    system = "x86_64-linux";
                    profiles = [ ];
                  };
                };
              };
            };
            rejectedApiToken = builtins.tryEval (
              lib.validateMachine "api-token" {
                system = "x86_64-linux";
                profiles = [ ];
                apiToken = "do-not-expose";
              }
            );
            rejectedPrivateKey = builtins.tryEval (
              lib.validateMachine "private-key" {
                system = "x86_64-linux";
                profiles = [ ];
                privateKey = "-----BEGIN PRIVATE KEY-----";
              }
            );
            rejectedStorePath = builtins.tryEval (
              lib.validateMachine "store-path" {
                system = "x86_64-linux";
                profiles = [ ];
                metadata.store = "/nix/store/unsafe-secret";
              }
            );
            rejectedFunction = builtins.tryEval (
              lib.validateMachine "function" {
                system = "x86_64-linux";
                profiles = [ ];
                metadata.transform = value: value;
              }
            );
            rejectedDerivation = builtins.tryEval (
              builtins.deepSeq (lib.registrySnapshot {
                digest = "sha256:executable";
                machines.derivation = {
                  system = "x86_64-linux";
                  profiles = [ ];
                  metadata.payload = builtins.derivation {
                    name = "manager-test";
                    system = "x86_64-linux";
                    builder = "/bin/sh";
                    args = [
                      "-c"
                      "touch $out"
                    ];
                  };
                };
              }) true
            );
          in
          assert valid.name == "fixture";
          assert valid.hostname == "fixture";
          assert !invalid.success;
          assert
            assembled.machineNames == [
              "fixture"
              "valid"
            ];
          assert assembled.configurations.fixture.config.networking.hostName == "fixture";
          assert pure.configurations.pure.config.networking.hostName == "pure-host";
          assert !(builtins.hasAttr "forced" pure.configurations.pure.config.arbor.machine);
          assert pure.machines.pure.machine.provenance.kind == "test";
          assert pure.machines.pure.machine.precedence == 7;
          assert pure.machines.pure.machine.cluster.relationshipData == [ "parent-a" ];
          assert !(builtins.hasAttr "clusterRole" lib.machineTypes);
          assert snapshot.machineNames == [ "snapshot" ];
          assert snapshot.configurations.snapshot.config.networking.hostName == "snapshot";
          assert !rejectedApiToken.success;
          assert !rejectedPrivateKey.success;
          assert !rejectedStorePath.success;
          assert !rejectedFunction.success;
          assert !rejectedDerivation.success;
          assert (import ./tests/node-selection.nix { inherit (nixpkgs) lib; });
          assert (import ./tests/snapshot.nix { inherit (nixpkgs) lib; });
          assert (import ./tests/source-merge.nix { inherit (nixpkgs) lib; });
          assert (import ./tests/colmena.nix { inherit (nixpkgs) lib; });
          (import nixpkgs { inherit system; }).emptyFile;
      });
    };
}
