{ lib }:
let
  predicateMatches =
    host: predicate:
    let
      actual = lib.attrByPath (predicate.path or [ ]) null host;
    in
    if predicate ? equals then
      actual == predicate.equals
    else if predicate ? notEquals then
      actual != predicate.notEquals
    else
      true;

  requirementEnabled =
    host: requirement:
    predicateMatches host (requirement.when or { });
in
{
  resolve =
    {
      dendriteRegistry,
      inventory,
    }:
    let
      byDendrite = lib.mapAttrs (
        _name: entry: entry.meta.identityRequirements or [ ]
      ) dendriteRegistry;
      byHost = lib.mapAttrs (
        _hostName: host:
        builtins.listToAttrs (
          lib.concatMap (
            dendriteName:
            builtins.map (
              requirement: {
                name = requirement.service;
                value = requirement // {
                  declaredBy = dendriteName;
                };
              }
            ) (
              builtins.filter (requirement: requirementEnabled host requirement) (
                byDendrite.${dendriteName} or [ ]
              )
            )
          ) (host.dendrites or [ ])
        )
      ) inventory.hosts;
    in
    {
      schema = "cluster.identity.requirements.v1";
      inherit byDendrite byHost;
    };
}
