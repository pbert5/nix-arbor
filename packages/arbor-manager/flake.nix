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
      mkCli =
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        pkgs.writeShellApplication {
          name = "arbor-manager";
          runtimeInputs = [
            pkgs.coreutils
            pkgs.jq
            pkgs.util-linux
          ];
          text = builtins.readFile ./bin/arbor-manager;
        };
      managerLib = import ./lib { inherit (nixpkgs) lib; };
      snapshot = import ./lib/snapshot.nix { inherit (nixpkgs) lib; };
      lib = managerLib // {
        inherit snapshot;
      };
    in
    {
      inherit lib;
      packages = forAllSystems (system: {
        arbor-manager = mkCli system;
        default = mkCli system;
      });
      apps = forAllSystems (system: {
        arbor-manager = {
          type = "app";
          program = "${mkCli system}/bin/arbor-manager";
        };
        default = {
          type = "app";
          program = "${mkCli system}/bin/arbor-manager";
        };
      });
      formatter = forAllSystems (system: (import nixpkgs { inherit system; }).nixfmt-tree);
      checks = forAllSystems (system: {
        cli =
          let
            pkgs = import nixpkgs { inherit system; };
            cli = mkCli system;
          in
          pkgs.runCommand "arbor-manager-cli-check"
            {
              nativeBuildInputs = [
                pkgs.coreutils
                pkgs.jq
              ];
            }
            ''
                work=$(mktemp -d)
                trap 'rm -rf "$work"' EXIT
                snapshot=$(jq -cnS '{
                  format: "arbor-manager/deployment-snapshot",
                  version: 1,
                  source: "test",
                  snapshot: {
                    roots: ["api"],
                    selector: "local",
                    selected: ["api"],
                    excluded: [{name: "db", reasons: ["outside-selector"]}],
                    nodes: {
                      api: {system: "x86_64-linux", profiles: ["server"], provenance: {kind: "test"}},
                      db: {system: "x86_64-linux", profiles: ["database"]}
                    }
                  }
                }')
                snapshot_digest=$(printf '%s' "$snapshot" | jq -cS '.snapshot' | sha256sum | cut -d' ' -f1)
                snapshot=$(jq --arg digest "$snapshot_digest" '. + {snapshotDigest: $digest}' <<<"$snapshot")
                digest=$(printf '%s' "$snapshot" | jq -cS 'del(.digest)' | sha256sum | cut -d' ' -f1)
                jq --arg digest "$digest" '. + {digest: $digest}' <<<"$snapshot" > "$work/snapshot.json"
              ${cli}/bin/arbor-manager nodes list --snapshot "$work/snapshot.json" --scope selected --format names > "$work/nodes"
                test "$(cat "$work/nodes")" = api
                ${cli}/bin/arbor-manager nodes list --snapshot "$work/snapshot.json" --scope local --format names > "$work/local"
                test "$(cat "$work/local")" = api
                ${cli}/bin/arbor-manager nodes list --snapshot "$work/snapshot.json" --scope selected --format table | grep -q '^NAME'
                ${cli}/bin/arbor-manager nodes list --snapshot "$work/snapshot.json" --scope selected --format ssh | grep -q '^root@api$'
                ${cli}/bin/arbor-manager nodes list --snapshot "$work/snapshot.json" --scope selected --format colmena | grep -q '^api$'
                ${cli}/bin/arbor-manager machine inspect --snapshot "$work/snapshot.json" --name api > "$work/inspect.json"
                jq -e '.format == "arbor-manager/machine-inspect" and .record.system == "x86_64-linux"' "$work/inspect.json"
                ${cli}/bin/arbor-manager deployment-plan --snapshot "$work/snapshot.json" --format text | grep -q 'deployment snapshot'
                touch "$out"
            '';
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
