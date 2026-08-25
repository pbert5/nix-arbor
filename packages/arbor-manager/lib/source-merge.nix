{ lib }:

let
  protectedFields = [
    "authority"
    "authorityRoot"
    "generation"
    "identity"
    "identityGeneration"
    "identity-generation"
  ];

  equal = a: b: builtins.toJSON a == builtins.toJSON b;

  canonicalize =
    value:
    if builtins.isAttrs value then
      builtins.listToAttrs (
        map (name: {
          inherit name;
          value = canonicalize value.${name};
        }) (builtins.sort builtins.lessThan (builtins.attrNames value))
      )
    else if builtins.isList value then
      map canonicalize value
    else
      value;

  asEntries =
    layer: value:
    if value == null then
      [ ]
    else if builtins.isList value then
      value
    else if builtins.isAttrs value then
      lib.mapAttrsToList (
        name: record:
        if builtins.isAttrs record && record ? record then
          record // { inherit name; }
        else
          {
            inherit name;
            inherit record;
          }
      ) value
    else
      throw "Arbor Manager: ${layer} source must be a list or attribute set.";

  checkedEntries =
    layer: value:
    let
      entries = asEntries layer value;
      step =
        seen: entry:
        if !(entry ? name) || !(builtins.isString entry.name) || entry.name == "" then
          throw "Arbor Manager: ${layer} source entries require a non-empty name."
        else if !(entry ? record) || !(builtins.isAttrs entry.record) then
          throw "Arbor Manager: ${layer} source '${entry.name}' requires an attribute-set record."
        else if builtins.elem entry.name seen then
          throw "Arbor Manager: duplicate ${layer} source name '${entry.name}'."
        else
          seen ++ [ entry.name ];
    in
    builtins.foldl' step [ ] entries;

  entryMap =
    layer: value:
    let
      entries = asEntries layer value;
      _ = checkedEntries layer value;
    in
    assert _ != null;
    builtins.listToAttrs (
      map (entry: {
        name = entry.name;
        value = entry;
      }) entries
    );

  fieldNames = record: builtins.filter (field: field != "provenance") (builtins.attrNames record);

  mergeAttrs =
    left: right:
    let
      names = builtins.sort builtins.lessThan (
        lib.unique ((builtins.attrNames left) ++ (builtins.attrNames right))
      );
    in
    builtins.listToAttrs (
      map (field: {
        name = field;
        value =
          if
            builtins.hasAttr field left
            && builtins.hasAttr field right
            && builtins.isAttrs left.${field}
            && builtins.isAttrs right.${field}
          then
            mergeAttrs left.${field} right.${field}
          else if builtins.hasAttr field right then
            right.${field}
          else
            left.${field};
      }) names
    );

  securityCheck =
    name: lower: base: overlay:
    let
      changed = builtins.filter (
        field:
        builtins.hasAttr field overlay
        && (!builtins.hasAttr field base || !(equal base.${field} overlay.${field}))
      ) protectedFields;
    in
    if changed != [ ] then
      throw "Arbor Manager: ${lower} source '${name}' attempts to change protected field(s): ${lib.concatStringsSep ", " changed}."
    else
      true;

  mergeRecord =
    name: registry: local: session:
    let
      registryRecord = if registry == null then { } else registry.record;
      localRecord = if local == null then { } else local.record;
      sessionRecord = if session == null then { } else session.record;
      _localSecurity =
        if local == null || registry == null then
          true
        else
          securityCheck name "committed local" registryRecord localRecord;
      _sessionSecurity =
        if session == null then
          true
        else
          securityCheck name "session override" (registryRecord // localRecord) sessionRecord;
      layers = [
        {
          label = "registry";
          entry = registry;
        }
        {
          label = "local";
          entry = local;
        }
        {
          label = "session";
          entry = session;
        }
      ];
      present = builtins.filter (item: item.entry != null) layers;
      record = builtins.foldl' (result: item: mergeAttrs result item.entry.record) { } present;
      fieldSources = builtins.listToAttrs (
        lib.concatMap (
          item:
          map (field: {
            name = field;
            value = {
              inherit field;
              layer = item.label;
              source = item.entry.provenance or { kind = item.label; };
            };
          }) (fieldNames item.entry.record)
        ) (lib.reverseList present)
      );
      source = {
        kind = "source-merge";
        layers = map (item: {
          layer = item.label;
          source = item.entry.provenance or { kind = item.label; };
        }) present;
      };
    in
    assert _localSecurity;
    assert _sessionSecurity;
    {
      inherit name;
      record = record // {
        provenance = {
          inherit source;
          fields = fieldSources;
        };
      };
      modules =
        (if local == null then [ ] else local.modules or [ ])
        ++ (if session == null then [ ] else session.modules or [ ]);
      provenance = source;
      precedence = 0;
    };

  resolveModules =
    trusted: entry:
    let
      selectors = entry.moduleSelectors or [ ];
      invalid = builtins.filter (
        selector: !(builtins.isString selector) || !(builtins.hasAttr selector trusted)
      ) selectors;
    in
    if entry ? modules then
      throw "Arbor Manager: session overrides may select trusted local modules with 'moduleSelectors', not provide 'modules'."
    else if invalid != [ ] then
      throw "Arbor Manager: unknown trusted local module selector(s): ${lib.concatStringsSep ", " (map toString invalid)}."
    else
      lib.concatMap (selector: trusted.${selector}) selectors;

  mergeSources =
    {
      registrySnapshot ? null,
      registry ? null,
      committedLocal ? null,
      local ? null,
      sessionOverride ? null,
      session ? null,
      trustedLocalModules ? { },
    }:
    let
      registryMap = entryMap "registry" (if registrySnapshot != null then registrySnapshot else registry);
      localMap = entryMap "committed local" (if committedLocal != null then committedLocal else local);
      rawSession = if sessionOverride != null then sessionOverride else session;
      sessionEntries = asEntries "session override" rawSession;
      _sessionNames = checkedEntries "session override" rawSession;
      sessionMap = builtins.listToAttrs (
        map (entry: {
          name = entry.name;
          value = entry // {
            modules = resolveModules trustedLocalModules entry;
          };
        }) sessionEntries
      );
      names = builtins.sort builtins.lessThan (
        lib.unique (
          (builtins.attrNames registryMap) ++ (builtins.attrNames localMap) ++ (builtins.attrNames sessionMap)
        )
      );
      get = map: name: if builtins.hasAttr name map then map.${name} else null;
      merged = map (
        name: mergeRecord name (get registryMap name) (get localMap name) (get sessionMap name)
      ) names;
      digestInput = canonicalize (
        builtins.listToAttrs (
          map (entry: {
            name = entry.name;
            value = entry.record;
          }) merged
        )
      );
    in
    assert _sessionNames != null;
    {
      sources = merged;
      machines = builtins.listToAttrs (
        map (entry: {
          name = entry.name;
          value = entry.record;
        }) merged
      );
      digest = builtins.hashString "sha256" (builtins.toJSON digestInput);
    };
in
{
  inherit mergeSources;
  sourceMerge = mergeSources;
}
