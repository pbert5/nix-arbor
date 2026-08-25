{ lib }:

let
  registry = import ../../packages/arbor-registry/lib { inherit lib; };
  manager = import ../../packages/arbor-manager/lib { inherit lib; };
  signer = registry.testSigner "root-A" "acceptance";

  record =
    {
      id,
      schema,
      subject ? null,
      generation ? 1,
      payload,
      features ? [ ],
    }:
    registry.makeEnvelope signer {
      recordId = id;
      inherit
        schema
        subject
        generation
        payload
        ;
      requiredFeatures = features;
      issuer = "root-A";
      createdAt = "2026-08-24T00:00:00Z";
    };

  relationship =
    {
      id,
      from,
      to,
      kind ? "parent",
      status ? "active",
    }:
    record {
      inherit id;
      schema = if kind == "peer" then "peer-relationship" else "relationship";
      subject = to;
      payload = {
        relationshipId = id;
        inherit
          from
          to
          kind
          status
          ;
        scope = [ "acceptance" ];
        autonomy = "dependent";
        priority = 1;
        authorityRoot = "root-A";
      };
    };

  records = [
    (record {
      id = "identity-root-A";
      schema = "node-identity";
      subject = "root-A";
      payload = {
        id = "root-A";
        aliases = [ "root" ];
      };
    })
    (record {
      id = "identity-parent-B";
      schema = "node-identity";
      subject = "parent-B";
      payload = {
        id = "parent-B";
        aliases = [ "parent" ];
      };
    })
    (relationship {
      id = "root-parent";
      from = "root-A";
      to = "parent-B";
    })
    (relationship {
      id = "parent-child-C";
      from = "parent-B";
      to = "child-C";
    })
    (relationship {
      id = "parent-child-D";
      from = "parent-B";
      to = "child-D";
    })
    (relationship {
      id = "parent-standby";
      from = "parent-B";
      to = "standby";
      kind = "standby-parent";
      status = "standby-parent";
    })
    (relationship {
      id = "child-peer-P";
      from = "child-C";
      to = "peer-P";
      kind = "peer";
    })
    (record {
      id = "endpoint-child-C";
      schema = "endpoint";
      subject = "child-C";
      payload = {
        id = "endpoint-child-C";
        node = "child-C";
        name = "api";
        protocol = "https";
        address = "child-c.example.test";
        port = 443;
        reachability = "private";
        policyRef = "api-read";
      };
    })
    (record {
      id = "service-api";
      schema = "service";
      subject = "child-C";
      payload = {
        id = "service-api";
        node = "child-C";
        name = "api";
        endpoint = "endpoint-child-C";
        policyRef = "api-read";
      };
    })
  ];

  base = registry.reconcile {
    raw = records;
    signers.root-A = signer;
    authorizedIssuers = [ "root-A" ];
  };
  transport = registry.makeDummyProvider records;
  converged = registry.reconcile {
    raw = transport.fetch { };
    signers.root-A = signer;
    authorizedIssuers = [ "root-A" ];
  };
  duplicate = transport.append (builtins.head records);

  unsupported = record {
    id = "compatibility-future";
    schema = "compatibility";
    subject = "child-D";
    features = [ "future-required-feature" ];
    payload = {
      protocolEpoch = 1;
      requiredFeatures = [ "future-required-feature" ];
    };
  };
  unsafe = record {
    id = "secret-boundary";
    schema = "service";
    subject = "child-C";
    payload = {
      id = "secret-boundary";
      name = "bad-service";
      token = "should-never-be-accepted";
    };
  };
  quarantine = registry.reconcile {
    raw = [
      unsupported
      unsafe
    ];
    signers.root-A = signer;
    authorizedIssuers = [ "root-A" ];
  };

  nodes = {
    root-A = {
      system = "x86_64-linux";
      profiles = [ ];
      criticalRoute = true;
      children = [ "parent-B" ];
    };
    parent-B = {
      system = "x86_64-linux";
      profiles = [ ];
      parents = [ "root-A" ];
      children = [
        "child-C"
        "child-D"
        "standby"
      ];
    };
    child-C = {
      system = "x86_64-linux";
      profiles = [ ];
      parents = [ "parent-B" ];
      children = [ "peer-P" ];
      endpoints = base.materialized.endpoints;
      services = base.materialized.services;
      compatibility = {
        protocolEpoch = 1;
      };
    };
    child-D = {
      system = "x86_64-linux";
      profiles = [ ];
      parents = [ "parent-B" ];
      compatible = false;
    };
    peer-P = {
      system = "x86_64-linux";
      profiles = [ ];
      parents = [ "child-C" ];
      compatible = false;
    };
    standby = {
      system = "x86_64-linux";
      profiles = [ ];
      parents = [ "parent-B" ];
      state = "standby";
    };
  };
  selected = manager.select {
    inherit nodes;
    roots = [ "root-A" ];
    selector = "accessible";
  };
  plan = manager.plan {
    inherit nodes;
    roots = [ "root-A" ];
    selector = "accessible";
    canary = "root-A";
    batchSize = 2;
  };
  source = manager.sourceMerge {
    registry = manager.registrySnapshot {
      digest = "sha256:acceptance";
      machines = {
        child-C = nodes.child-C;
      };
    };
    local = [
      {
        name = "child-C";
        record.hostname = "local-child-c";
      }
    ];
    sessionOverride = [
      {
        name = "child-C";
        record.metadata.acceptance = true;
      }
    ];
  };
  recovery = registry.recoveryAuthorization {
    identity = "parent-B";
    lostGeneration = registry.identityGeneration {
      identity = "parent-B";
      generation = 1;
      authority = [
        "observe"
        "recover"
      ];
    };
    newGeneration = registry.identityGeneration {
      identity = "parent-B";
      generation = 2;
      predecessor = "parent-B:1";
      authority = [ "observe" ];
    };
    operator = "operator";
    operatorApproval = registry.approvalRecord {
      approver = "operator";
      role = "operator";
      subject = "parent-B";
      issuer = "operator-authority";
      generation = 1;
      operation = "recovery";
      signature = "signed-operator-approval";
    };
  };
  recoveryRevoked = recovery // {
    revocations = [
      (registry.revocation {
        identity = "parent-B";
        generation = 1;
        issuer = "root-A";
        reason = "lost-key";
      })
    ];
  };
  unsafeOverride = builtins.tryEval (
    builtins.deepSeq (manager.sourceMerge {
      registry = manager.registrySnapshot {
        digest = "sha256:acceptance";
        machines = {
          child-C = nodes.child-C;
        };
      };
      sessionOverride = [
        {
          name = "child-C";
          record.identityGeneration = 99;
        }
      ];
    }) true
  );
  unsafePlan = builtins.tryEval (
    builtins.deepSeq (manager.plan {
      nodes = nodes // {
        "bad;node" = nodes.child-C;
      };
      roots = [ "bad;node" ];
    }) true
  );
in
assert base.quarantined == [ ];
assert converged.graph == base.graph;
assert converged.materialized.endpoints == base.materialized.endpoints;
assert converged.materialized.services == base.materialized.services;
assert
  lib.sortOn (x: x.relationshipId) converged.materialized.relationships
  == lib.sortOn (x: x.relationshipId) base.materialized.relationships;
assert duplicate.snapshot == transport.snapshot;
assert base.graph.cycles == [ ];
assert base.graph.multipleParents == [ ];
assert
  registry.graphQuery {
    relationships = base.materialized.relationships;
    from = "root-A";
    selector = "descendants";
  } == [
    "parent-B"
    "child-C"
    "child-D"
  ];
assert
  registry.graphQuery {
    relationships = base.materialized.relationships;
    from = "child-C";
    selector = "peers";
  } == [ "peer-P" ];
assert builtins.length base.materialized.endpoints == 1;
assert builtins.length base.materialized.services == 1;
assert (builtins.head base.materialized.services).endpoint == "endpoint-child-C";
assert (builtins.head quarantine.quarantined).quarantine.code == "unsupported-required-feature";
assert (builtins.elemAt quarantine.quarantined 1).quarantine.code == "unsafe-value";
assert
  selected.selected == [
    "root-A"
    "parent-B"
    "child-C"
  ];
assert
  (builtins.head (builtins.filter (x: x.name == "child-D") selected.excluded)).reasons
  == [ "incompatible" ];
assert
  (builtins.head (builtins.filter (x: x.name == "standby") selected.excluded)).reasons
  == [ "standby-not-allowed" ];
assert
  plan.phases == [
    {
      name = "canary";
      names = [ "root-A" ];
      commands = [ "nixos-rebuild switch --flake '.#root-A'" ];
    }
    {
      name = "batches";
      names = [
        [
          "parent-B"
          "child-C"
        ]
      ];
      commands = [
        [
          "nixos-rebuild switch --flake '.#parent-B'"
          "nixos-rebuild switch --flake '.#child-C'"
        ]
      ];
    }
  ];
assert (builtins.filter (risk: risk.kind == "critical-route") plan.risks) != [ ];
assert source.digest != "";
assert (builtins.head source.sources).record.hostname == "local-child-c";
assert (builtins.head source.sources).record.metadata.acceptance;
assert (builtins.head source.sources).record.provenance.fields.hostname.layer == "local";
assert recovery.authorized;
assert
  !registry.generationUsable {
    generation = recovery.lostGeneration;
    revocations = recoveryRevoked.revocations;
  };
assert !unsafeOverride.success;
assert !unsafePlan.success;
true
