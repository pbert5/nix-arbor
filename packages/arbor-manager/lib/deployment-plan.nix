{ lib, nodeSelection }:

let
  sortUnique = values: lib.unique (builtins.sort builtins.lessThan values);

  chunks =
    size: values:
    if values == [ ] then [ ] else [ (lib.take size values) ] ++ chunks size (lib.drop size values);

  jsonDigest = value: builtins.hashString "sha256" (builtins.toJSON value);

  validateTargetName =
    name:
    if builtins.match "^[A-Za-z0-9._-]+$" name == null then
      throw "Arbor Manager: node name '${name}' is unsafe for deployment commands."
    else
      name;

  validateBackend =
    backend:
    if
      builtins.elem backend [
        "direct"
        "colmena"
      ]
    then
      backend
    else
      throw "Arbor Manager: unknown deployment backend '${toString backend}'.";

  riskFor =
    nodes: selected:
    let
      critical = builtins.filter (
        name: (nodes.${name}.criticalRoute or false) || (nodes.${name}.critical or false)
      ) selected;
      standby = builtins.filter (name: (nodes.${name}.state or "active") == "standby") selected;
      suspended = builtins.filter (name: (nodes.${name}.state or "active") == "suspended") selected;
    in
    (lib.optional (critical != [ ]) {
      kind = "critical-route";
      severity = "high";
      nodes = critical;
      message = "Selection includes nodes on a critical route.";
    })
    ++ (lib.optional (standby != [ ]) {
      kind = "standby";
      severity = "medium";
      nodes = standby;
      message = "Selection includes standby nodes.";
    })
    ++ (lib.optional (suspended != [ ]) {
      kind = "suspended";
      severity = "high";
      nodes = suspended;
      message = "Selection includes suspended nodes.";
    });

  backendRecommendation =
    nodes: selected: requested:
    if requested != null then
      {
        backend = validateBackend requested;
        reason = "Explicit backend choice.";
      }
    else if selected == [ ] then
      {
        backend = "direct";
        reason = "Empty selection has no backend fan-out.";
      }
    else if builtins.all (name: (nodes.${name}.backend or null) == "colmena") selected then
      {
        backend = "colmena";
        reason = "Every selected node declares the Colmena interface.";
      }
    else
      {
        backend = "direct";
        reason = "Direct is the conservative default for mixed or unspecified interfaces.";
      };

  commandFor =
    backend: name:
    if backend == "colmena" then
      "colmena apply --on '${name}'"
    else
      "nixos-rebuild switch --flake '.#${name}'";

  commandForBatch = backend: names: [ (commandFor backend (lib.concatStringsSep " " names)) ];

in
rec {
  planFromSnapshot =
    {
      snapshot,
      roots ? null,
      selector ? "local",
      backend ? null,
      canary ? null,
      batchSize ? 1,
      allowStandby ? false,
      allowSuspended ? false,
    }:
    let
      nodes =
        if snapshot ? snapshot && snapshot.snapshot ? nodes then
          snapshot.snapshot.nodes
        else if snapshot ? nodes then
          snapshot.nodes
        else if snapshot ? machines then
          snapshot.machines
        else
          throw "Arbor Manager: snapshot must contain nodes, machines, or snapshot.nodes.";
      selectedRoots = if roots == null then builtins.attrNames nodes else roots;
    in
    plan {
      inherit
        nodes
        selector
        backend
        canary
        batchSize
        allowStandby
        allowSuspended
        ;
      roots = selectedRoots;
    };

  plan =
    {
      nodes,
      roots,
      selector ? "local",
      backend ? null,
      canary ? null,
      batchSize ? 1,
      allowStandby ? false,
      allowSuspended ? false,
    }:
    let
      selection = nodeSelection.select {
        inherit
          nodes
          roots
          selector
          allowStandby
          allowSuspended
          ;
      };
      selected = builtins.deepSeq (map validateTargetName selection.selected) selection.selected;
      validBatchSize =
        if !(builtins.isInt batchSize) || batchSize <= 0 then
          throw "Arbor Manager: batchSize must be a positive integer."
        else
          batchSize;
      checkedCanary =
        if canary == null then
          null
        else if !(builtins.isString canary) then
          throw "Arbor Manager: canary must be a node name or null."
        else if !(builtins.elem canary selected) then
          throw "Arbor Manager: canary '${canary}' is not in the deployable selection."
        else if
          builtins.any (
            parent: builtins.elem parent selected && builtins.elem canary (selection.graphValue.children parent)
          ) selection.graphValue.names
        then
          throw "Arbor Manager: canary '${canary}' violates topological ordering; selected parent(s) must deploy first."
        else
          canary;
      chosenCanary =
        if checkedCanary != null then
          [ checkedCanary ]
        else if selected != [ ] then
          [ (builtins.head selected) ]
        else
          [ ];
      remaining = builtins.filter (name: !(builtins.elem name chosenCanary)) selected;
      batches = chunks validBatchSize remaining;
      recommendation = backendRecommendation nodes selected backend;
      risks = riskFor nodes selected;
      phases =
        (lib.optional (chosenCanary != [ ]) {
          name = "canary";
          names = chosenCanary;
          commands = map (commandFor recommendation.backend) chosenCanary;
        })
        ++ (lib.optional (batches != [ ]) {
          name = "batches";
          names = batches;
          commands = map (commandForBatch recommendation.backend) batches;
        });
      snapshot = {
        inherit roots selector selected;
        excluded = selection.excluded;
        nodes = builtins.listToAttrs (
          map (name: {
            inherit name;
            value = nodes.${name};
          }) (sortUnique (selection.selectedByRelation ++ selected))
        );
      };
      snapshotDigest = jsonDigest snapshot;
      acknowledgement = {
        digest = jsonDigest {
          inherit snapshotDigest phases risks;
          backend = recommendation.backend;
        };
        token = "arbor-manager/v1:${snapshotDigest}:${
          jsonDigest {
            inherit snapshotDigest phases risks;
            backend = recommendation.backend;
          }
        }";
        names = lib.concatStringsSep "\n" selected;
        commands = lib.concatMap (phase: phase.commands) phases;
      };
    in
    builtins.seq validBatchSize (
      builtins.seq checkedCanary (
        builtins.seq recommendation.backend {
          inherit
            selection
            snapshot
            snapshotDigest
            phases
            acknowledgement
            ;
          backend = recommendation;
          inherit risks;
          names = selected;
          commands = acknowledgement.commands;
          inspect = {
            snapshotDigest = snapshotDigest;
            acknowledgementDigest = acknowledgement.digest;
            names = acknowledgement.names;
            commands = acknowledgement.commands;
          };
        }
      )
    );
}
