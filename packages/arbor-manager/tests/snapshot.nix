{ lib }:
let
  manager = import ../lib { inherit lib; };
  snapshot = import ../lib/snapshot.nix { inherit lib; };
  resolved = {
    machine = {
      name = "edge";
      system = "x86_64-linux";
      profiles = [ "server" ];
      provenance = {
        kind = "registry-snapshot";
        digest = "sha256:registry";
      };
      metadata = {
        z = 1;
        a = 2;
        apiToken = "do-not-export";
        transform = value: value;
        nested = [
          { endpoint = "https://user:password@example.invalid/api"; }
          { query = "https://example.invalid/api?access_token=secret"; }
          { bearer = "Bearer nested-secret"; }
        ];
      };
    };
  };
  inspected = snapshot.inspectMachine { machine = resolved; };
  exported = snapshot.exportMachine { machine = resolved; };
  plan = manager.plan {
    nodes = {
      edge = { };
    };
    roots = [ "edge" ];
  };
  deployment = snapshot.deploymentSnapshot { inherit plan; };
in
assert
  (snapshot.canonicalJson ({
    z = 1;
    a = 2;
  })) == (snapshot.canonicalJson ({
    a = 2;
    z = 1;
  }));
assert
  (snapshot.digest ({
    z = 1;
    a = 2;
  })) == (snapshot.digest ({
    a = 2;
    z = 1;
  }));
assert inspected.provenance.source.kind == "registry-snapshot";
assert inspected.provenance.fields.metadata.source.digest == "sha256:registry";
assert inspected.provenance.fields.metadata.field == "metadata";
assert inspected.record.metadata.apiToken == "<redacted>";
assert inspected.record.metadata.transform == "<redacted>";
assert
  inspected.record.metadata.nested == [
    { endpoint = "<redacted>"; }
    { query = "<redacted>"; }
    { bearer = "<redacted>"; }
  ];
assert builtins.match ".*apiToken.*<redacted>.*" exported != null;
assert builtins.match ".*transform.*<redacted>.*" exported != null;
assert builtins.match ".*do-not-export.*" exported == null;
assert builtins.match ".*user:password.*" exported == null;
assert builtins.match ".*access_token=secret.*" exported == null;
assert builtins.match ".*nested-secret.*" exported == null;
assert
  snapshot.digest {
    nested = "https://one:secret@example.invalid";
    bearer = "Bearer first";
  } == snapshot.digest {
    nested = "https://two:other@example.invalid";
    bearer = "Bearer second";
  };
assert
  builtins.match ".*/nix/store/.*" (
    snapshot.exportMachine {
      machine = {
        machine = resolved.machine // {
          metadata.store = "/nix/store/nope";
        };
      };
    }
  ) == null;
assert deployment.format == "arbor-manager/deployment-snapshot";
assert deployment.snapshotDigest == plan.snapshotDigest;
assert deployment.digest == (snapshot.digest (builtins.removeAttrs deployment [ "digest" ]));
assert deployment.plan.backend == plan.backend.backend;
assert deployment.plan.phases == plan.phases;
assert deployment.acknowledgement.digest == plan.acknowledgement.digest;
assert deployment.acknowledgement.token == plan.acknowledgement.token;
assert
  (builtins.head (
    manager.registrySnapshot {
      digest = "sha256:registry";
      machines.edge = {
        system = "x86_64-linux";
        profiles = [ ];
      };
    }
  )).modules == [ ];
true
