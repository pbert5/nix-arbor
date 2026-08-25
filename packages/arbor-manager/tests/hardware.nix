{ lib }:
let
  manager = import ../lib { inherit lib; };
  snapshot = import ../lib/snapshot.nix { inherit lib; };
  validSnapshot = manager.validateMachine "snapshot" {
    system = "x86_64-linux";
    profiles = [ ];
    hardware = {
      snapshot = {
        format = "arbor/hardware";
        version = 1;
        facts = {
          memoryBytes = 17179869184;
          cpu = "x86_64-v3";
        };
      };
    };
  };
  validArtifact = manager.validateMachine "artifact" {
    system = "aarch64-linux";
    profiles = [ ];
    hardware = {
      artifact = {
        digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        mediaType = "application/vnd.arbor.hardware+json";
      };
    };
  };
  registry = manager.registrySnapshot {
    digest = "sha256:registry";
    machines.registry = validSnapshot;
  };
  inspected = snapshot.inspectMachine {
    machine = (builtins.head registry).record;
    source = (builtins.head registry).provenance;
  };
  rejectedRegistry = builtins.tryEval (
    builtins.deepSeq (manager.registrySnapshot {
      digest = "sha256:registry";
      machines.invalid = {
        system = "x86_64-linux";
        profiles = [ ];
        hardware.artifact.digest = "sha256:not-content-addressed";
      };
    }) true
  );
  rejected =
    value: builtins.tryEval (builtins.deepSeq (manager.validateMachine "invalid" value) true);
in
assert validSnapshot.hardware.snapshot.facts.cpu == "x86_64-v3";
assert inspected.record.hardware.snapshot.format == "arbor/hardware";
assert inspected.provenance.fields.hardware.source.digest == "sha256:registry";
assert !rejectedRegistry.success;
assert
  validArtifact.hardware.artifact.digest
  == "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
assert
  !(rejected {
    system = "x86_64-linux";
    profiles = [ ];
    hardware.artifact.digest = "sha256:not-content-addressed";
  }).success;
assert
  !(rejected {
    system = "x86_64-linux";
    profiles = [ ];
    hardware.modules = [ ./fixtures/fixture/configuration.nix ];
  }).success;
assert
  !(rejected {
    system = "x86_64-linux";
    profiles = [ ];
    hardware = {
      snapshot = {
        format = "arbor/hardware";
        version = 1;
        facts = { };
      };
      artifact.digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    };
  }).success;
true
