{ lib }:

let
  manager = import ../lib { inherit lib; };
  nodes = {
    api = {
      children = [ "worker" ];
      criticalRoute = true;
    };
    worker = {
      parents = [ "api" ];
      children = [ "db" ];
    };
    db = {
      parents = [ "worker" ];
      reachable = false;
    };
    standby = {
      parents = [ "api" ];
      state = "standby";
    };
    suspended = {
      parents = [ "api" ];
      state = "suspended";
    };
    isolated = {
      compatible = false;
    };
    cycle-a = {
      children = [ "cycle-b" ];
    };
    cycle-b = {
      children = [ "cycle-a" ];
    };
  };
  g = manager.graph nodes;
  fails = expression: !(builtins.tryEval (builtins.deepSeq expression true)).success;
  plan = manager.plan {
    inherit nodes;
    roots = [ "api" ];
    selector = "accessible";
    batchSize = 1;
  };
  snapshotPlan = manager.planFromSnapshot {
    snapshot = { inherit nodes; };
    roots = [ "api" ];
    selector = "accessible";
    batchSize = 1;
  };
in
assert manager.selectors.local g [ "api" ] == [ "api" ];
assert
  manager.selectors.children g [ "api" ] == [
    "standby"
    "suspended"
    "worker"
  ];
assert
  manager.selectors.descendants g [ "api" ] == [
    "db"
    "standby"
    "suspended"
    "worker"
  ];
assert manager.selectors.parents g [ "db" ] == [ "worker" ];
assert
  manager.selectors.ancestors g [ "db" ] == [
    "api"
    "worker"
  ];
assert
  manager.selectors.accessible g [ "cycle-a" ] == [
    "cycle-a"
    "cycle-b"
  ];
assert
  (manager.select {
    inherit nodes;
    roots = [ "api" ];
    selector = "descendants";
  }).selected == [ "worker" ];
assert
  (builtins.head (builtins.filter (entry: entry.name == "db") plan.selection.excluded)).reasons
  == [ "unreachable" ];
assert
  (builtins.head (builtins.filter (entry: entry.name == "standby") plan.selection.excluded)).reasons
  == [ "standby-not-allowed" ];
assert
  (builtins.head (builtins.filter (entry: entry.name == "suspended") plan.selection.excluded)).reasons
  == [ "suspended-not-allowed" ];
assert
  plan.names == [
    "api"
    "worker"
  ];
assert plan.backend.backend == "direct";
assert snapshotPlan.names == plan.names;
assert snapshotPlan.snapshotDigest == plan.snapshotDigest;
assert (builtins.filter (risk: risk.kind == "critical-route") plan.risks) != [ ];
assert
  plan.phases == [
    {
      name = "canary";
      names = [ "api" ];
      commands = [ "nixos-rebuild switch --flake '.#api'" ];
    }
    {
      name = "batches";
      names = [ [ "worker" ] ];
      commands = [ [ "nixos-rebuild switch --flake '.#worker'" ] ];
    }
  ];
assert
  plan.snapshotDigest == (manager.plan {
    inherit nodes;
    roots = [ "api" ];
    selector = "accessible";
    batchSize = 1;
  }).snapshotDigest;
assert plan.acknowledgement.digest != "";
assert builtins.match ".*api.*" plan.inspect.names != null;
assert builtins.match ".*worker.*" (builtins.head plan.inspect.commands) == null;
let
  reversed = {
    z-parent = {
      children = [ "a-child" ];
    };
    a-child = {
      parents = [ "z-parent" ];
    };
  };
  reversedPlan = manager.plan {
    nodes = reversed;
    roots = [ "z-parent" ];
    selector = "accessible";
    canary = "z-parent";
  };
  cyclePlan = manager.plan {
    inherit nodes;
    roots = [ "cycle-a" ];
    selector = "accessible";
  };
  unsafeNodes = {
    "bad;name" = { };
  };
in
assert
  reversedPlan.names == [
    "z-parent"
    "a-child"
  ];
assert
  reversedPlan.phases == [
    {
      name = "canary";
      names = [ "z-parent" ];
      commands = [ "nixos-rebuild switch --flake '.#z-parent'" ];
    }
    {
      name = "batches";
      names = [ [ "a-child" ] ];
      commands = [ [ "nixos-rebuild switch --flake '.#a-child'" ] ];
    }
  ];
assert fails (
  manager.plan {
    nodes = reversed;
    roots = [ "z-parent" ];
    selector = "accessible";
    canary = "a-child";
  }
);
assert cyclePlan.names == [ ];
assert
  cyclePlan.selection.blocked == [
    "cycle-a"
    "cycle-b"
  ];
assert
  (builtins.head (builtins.filter (entry: entry.name == "cycle-a") cyclePlan.selection.excluded))
  .reasons == [ "cycle-blocked" ];
assert fails (
  manager.select {
    inherit nodes;
    roots = [ "missing" ];
  }
);
assert fails (
  manager.graph {
    malformed = {
      children = "not-a-list";
    };
  }
);
assert fails (
  manager.plan {
    inherit nodes;
    roots = [ "api" ];
    backend = "unknown";
  }
);
assert fails (
  manager.plan {
    inherit nodes;
    roots = [ "api" ];
    canary = "missing";
  }
);
assert fails (
  manager.plan {
    inherit nodes;
    roots = [ "api" ];
    batchSize = 0;
  }
);
assert fails (
  manager.plan {
    nodes = {
      invalid = {
        state = "draining";
      };
    };
    roots = [ "invalid" ];
  }
);
assert fails (
  manager.plan {
    nodes = unsafeNodes;
    roots = [ "bad;name" ];
  }
);
true
