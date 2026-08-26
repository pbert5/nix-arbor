{ lib }:

let
  redacted = "<redacted>";
  secretKey =
    name:
    lib.elem (lib.toLower (builtins.replaceStrings [ "-" "_" ] [ "" "" ] name)) [
      "secret"
      "password"
      "passphrase"
      "token"
      "credential"
      "privatekey"
      "signingkey"
      "apikey"
      "apitoken"
      "accesstoken"
      "seed"
    ];
  unsafeString =
    value:
    let
      lower = lib.toLower value;
      isUrl = builtins.match "^[A-Za-z][A-Za-z0-9+.-]*://.*" value != null;
      hasUrlUserinfo =
        builtins.match "^[A-Za-z][A-Za-z0-9+.-]*://[^/?#[:space:]]+:[^/?#[:space:]]+@.*" value != null;
      hasSecretQuery =
        isUrl
        &&
          builtins.match ".*[?&](token|password|secret|credential|api[_-]?key|access[_-]?key|access[_-]?token|private[_-]?key|signing[_-]?key|pass[_-]?phrase|seed)=[^&]*.*" lower
          != null;
      isBearer = builtins.match "^bearer[[:space:]]+[^[:space:]]+$" lower != null;
    in
    lib.hasPrefix "/nix/store/" value
    || lib.hasPrefix "/run/secrets/" value
    || lib.hasPrefix "/run/credentials/" value
    || lib.hasPrefix "/var/run/secrets/" value
    || lib.hasPrefix "-----BEGIN" value
    || hasUrlUserinfo
    || hasSecretQuery
    || isBearer;
  redact =
    value:
    let
      type = builtins.typeOf value;
    in
    if builtins.isFunction value || type == "path" then
      redacted
    else if builtins.isAttrs value then
      if (value.type or null) == "derivation" || builtins.hasAttr "__functor" value then
        redacted
      else
        builtins.listToAttrs (
          map (name: {
            inherit name;
            value = if secretKey name then redacted else redact value.${name};
          }) (builtins.attrNames value)
        )
    else if builtins.isList value then
      map redact value
    else if builtins.isString value && unsafeString value then
      redacted
    else
      value;
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
  public = value: canonicalize (redact value);
  canonicalJson = value: builtins.toJSON (public value);
  digest = value: builtins.hashString "sha256" (canonicalJson value);
  resolvedRecord = machine: if builtins.hasAttr "machine" machine then machine.machine else machine;
  machineName = machine: (resolvedRecord machine).name or "unknown";
  sourceFor =
    machine: source:
    if source != null then source else ((resolvedRecord machine).provenance or { kind = "resolved"; });
  inspectMachine =
    {
      machine,
      source ? null,
    }:
    let
      rawRecord = resolvedRecord machine;
      record = public rawRecord;
      sourceProvenance = public (sourceFor machine source);
      fields = builtins.listToAttrs (
        map (field: {
          name = field;
          value = {
            inherit field;
            source = sourceProvenance;
          };
        }) (builtins.attrNames rawRecord)
      );
    in
    {
      format = "arbor-manager/machine-inspect";
      version = 1;
      name = machineName machine;
      provenance = {
        source = sourceProvenance;
        inherit fields;
      };
      inherit record;
    };
  deploymentSnapshot =
    {
      plan,
      source ? "deployment-plan",
    }:
    let
      snapshot = if plan ? snapshot then plan.snapshot else plan;
      body = {
        format = "arbor-manager/deployment-snapshot";
        version = 1;
        inherit source;
        inherit snapshot;
        snapshotDigest = if plan ? snapshotDigest then plan.snapshotDigest else digest snapshot;
        plan = {
          backend = if plan ? backend then plan.backend.backend else "direct";
          phases = plan.phases or [ ];
          risks = plan.risks or [ ];
        };
        acknowledgement = plan.acknowledgement or null;
      };
    in
    body // { digest = digest body; };
in
{
  inherit
    canonicalJson
    canonicalize
    digest
    deploymentSnapshot
    inspectMachine
    public
    ;
  exportMachine = args: canonicalJson (inspectMachine args);
  exportDeployment = args: canonicalJson (deploymentSnapshot args);
}
