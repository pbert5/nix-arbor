{ lib }:

let
  jsonDigest = value: builtins.hashString "sha256" (builtins.toJSON value);

  targetFields = [
    "targetHost"
    "targetPort"
    "targetUser"
  ];

  targetValue =
    record: field:
    if builtins.hasAttr field record then
      record.${field}
    else if builtins.hasAttr "target" record && builtins.hasAttr field record.target then
      record.target.${field}
    else
      null;

  node =
    machines: name:
    let
      machine = machines.${name};
      record = machine.machine;
      deployment = lib.filterAttrs (_: value: value != null) (
        lib.genAttrs targetFields (field: targetValue record field)
      );
    in
    {
      imports = machine.modules;
      inherit deployment;
      tags = record.tags or [ ];
    };
in
{
  rawHive =
    {
      machines,
      plan,
      snapshotDigest ? null,
      meta ? { },
    }:
    let
      selected = plan.names;
      missing = builtins.filter (name: !(builtins.hasAttr name machines)) selected;
      backend = if plan ? backend && plan.backend ? backend then plan.backend.backend else null;
      expectedSnapshot = if plan ? snapshot then plan.snapshot else null;
      expectedMachines =
        if expectedSnapshot == null then
          null
        else
          builtins.listToAttrs (
            map (name: {
              inherit name;
              value = expectedSnapshot.nodes.${name};
            }) selected
          );
      actualMachines = builtins.listToAttrs (
        map (name: {
          inherit name;
          value = machines.${name}.machine;
        }) selected
      );
    in
    assert lib.assertMsg (
      backend == "colmena"
    ) "Arbor Manager: Colmena projection requires a plan bound to the Colmena backend.";
    assert lib.assertMsg (
      builtins.isString snapshotDigest && snapshotDigest != ""
    ) "Arbor Manager: Colmena projection requires an explicit snapshot digest.";
    assert lib.assertMsg (
      plan ? snapshotDigest
      && plan.snapshotDigest == snapshotDigest
      && expectedSnapshot != null
      && jsonDigest expectedSnapshot == plan.snapshotDigest
    ) "Arbor Manager: Colmena projection snapshot digest does not match the deployment plan.";
    assert lib.assertMsg (
      missing == [ ]
    ) "Arbor Manager: Colmena plan selected unknown machine(s): ${lib.concatStringsSep ", " missing}.";
    assert lib.assertMsg (
      jsonDigest actualMachines == jsonDigest expectedMachines
    ) "Arbor Manager: Colmena machines do not match the deployment plan snapshot.";
    {
      meta = meta // {
        arbor = (meta.arbor or { }) // {
          backend = backend;
          inherit snapshotDigest selected;
        };
      };
    }
    // builtins.listToAttrs (
      map (name: {
        inherit name;
        value = node machines name;
      }) selected
    );

  selection = plan: plan.names;
}
