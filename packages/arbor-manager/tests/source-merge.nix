{ lib }:
let
  manager = import ../lib { inherit lib; };
  module = { ... }: { };
  registry = manager.registrySnapshot {
    digest = "sha256:registry";
    machines.node = {
      system = "x86_64-linux";
      profiles = [ ];
      hostname = "registry-name";
      identity = "node-1";
      identityGeneration = 4;
      metadata = {
        registry = true;
      };
    };
  };
  local = [
    {
      name = "node";
      record = {
        hostname = "local-name";
        metadata.local = true;
      };
      modules = [ ./fixtures/fixture/configuration.nix ];
      provenance = {
        kind = "committed-local";
        revision = "abc";
      };
    }
  ];
  override = [
    {
      name = "node";
      record = {
        hostname = "cli-name";
        metadata.cli = true;
      };
      moduleSelectors = [ "trusted" ];
    }
  ];
  merged = manager.sourceMerge {
    inherit registry local;
    sessionOverride = override;
    trustedLocalModules.trusted = [ module ];
  };
  machine = builtins.head merged.sources;
  rejectedSecurity = builtins.tryEval (
    builtins.deepSeq (manager.sourceMerge {
      inherit registry local;
      sessionOverride = [
        {
          name = "node";
          record = {
            identityGeneration = 5;
          };
        }
      ];
    }) true
  );
  rejectedDuplicate = builtins.tryEval (
    builtins.deepSeq (manager.sourceMerge {
      registry = registry ++ registry;
    }) true
  );
  rejectedNestedSecurity = builtins.tryEval (
    builtins.deepSeq (manager.sourceMerge {
      inherit registry local;
      sessionOverride = [
        {
          name = "node";
          record = {
            metadata.identity = "unsafe";
          };
        }
      ];
    }) true
  );
  rejectedModules = builtins.tryEval (
    builtins.deepSeq (manager.sourceMerge {
      inherit registry;
      sessionOverride = [
        {
          name = "node";
          record = {
            hostname = "unsafe";
          };
          modules = [ module ];
        }
      ];
    }) true
  );
  registryOnly = manager.sourceMerge { inherit registry; };
  localOnly = manager.sourceMerge { inherit local; };
  mergedAgain = manager.sourceMerge {
    inherit registry local;
    sessionOverride = override;
    trustedLocalModules.trusted = [ module ];
  };
in
assert (builtins.head registryOnly.sources).record.hostname == "registry-name";
assert (builtins.head localOnly.sources).record.hostname == "local-name";
assert machine.record.hostname == "cli-name";
assert machine.record.system == "x86_64-linux";
assert
  machine.record.metadata.registry && machine.record.metadata.local && machine.record.metadata.cli;
assert machine.record.provenance.fields.system.layer == "registry";
assert machine.record.provenance.fields.hostname.layer == "session";
assert machine.record.provenance.fields.metadata.layer == "session";
assert machine.record.provenance.fields.system.source.digest == "sha256:registry";
assert builtins.length machine.modules == 2;
assert builtins.head machine.modules == ./fixtures/fixture/configuration.nix;
assert !rejectedSecurity.success;
assert !rejectedDuplicate.success;
assert !rejectedNestedSecurity.success;
assert !rejectedModules.success;
assert merged.digest == mergedAgain.digest;
true
