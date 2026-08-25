{ lib }:

let
  manager = import ../lib { inherit lib; };
  machines = {
    api = {
      machine = {
        name = "api";
        system = "x86_64-linux";
        targetHost = "api.example";
        targetPort = 2222;
        targetUser = "deploy";
        tags = [
          "web"
          "blue"
        ];
      };
      modules = [ ];
    };
    worker = {
      machine = {
        name = "worker";
        system = "x86_64-linux";
        target = {
          targetHost = "worker.example";
          targetUser = "worker";
        };
        tags = [ "jobs" ];
      };
      modules = [ ];
    };
  };
  plan = manager.plan {
    nodes = {
      api = machines.api.machine;
      worker = machines.worker.machine;
      excluded = {
        reachable = false;
      };
    };
    roots = [ "api" ];
    selector = "local";
    backend = "colmena";
  };
  hive = manager.rawHive {
    inherit machines plan;
    snapshotDigest = plan.snapshotDigest;
  };
  directPlan = manager.plan {
    nodes = {
      api = { };
    };
    roots = [ "api" ];
    backend = "direct";
  };
in
assert plan.names == [ "api" ];
assert !(builtins.hasAttr "worker" hive);
assert !(builtins.hasAttr "excluded" hive);
assert
  hive.api.deployment == {
    targetHost = "api.example";
    targetPort = 2222;
    targetUser = "deploy";
  };
assert
  hive.api.tags == [
    "web"
    "blue"
  ];
assert hive.meta.arbor.backend == "colmena";
assert hive.meta.arbor.snapshotDigest == plan.snapshotDigest;
assert hive.meta.arbor.selected == [ "api" ];
assert directPlan.backend.backend == "direct";
assert plan.backend.backend == "colmena";
assert
  !(builtins.tryEval (
    builtins.deepSeq (manager.rawHive {
      inherit machines plan;
      snapshotDigest = "stale";
    }) true
  )).success;
assert
  !(builtins.tryEval (
    builtins.deepSeq (manager.rawHive {
      machines = machines // {
        api.machine.targetHost = "stale.example";
      };
      inherit plan;
      snapshotDigest = plan.snapshotDigest;
    }) true
  )).success;
assert
  !(builtins.tryEval (
    builtins.deepSeq (manager.rawHive {
      inherit machines;
      plan = directPlan;
      snapshotDigest = directPlan.snapshotDigest;
    }) true
  )).success;
true
