{ lib }:

let
  artifactFields = [
    "digest"
    "mediaType"
    "size"
    "uri"
  ];

  rejectUnknown =
    context: allowed: value:
    let
      unknown = builtins.filter (field: !(builtins.elem field allowed)) (builtins.attrNames value);
    in
    if unknown != [ ] then
      throw "Arbor Manager: ${context} contains unsupported field(s): ${lib.concatStringsSep ", " unknown}."
    else
      true;

  validateArtifact =
    validatePublicValue: context: artifact:
    if !builtins.isAttrs artifact then
      throw "Arbor Manager: ${context} must be an attribute set."
    else
      let
        _fields = rejectUnknown context artifactFields artifact;
        digest = artifact.digest or null;
        size = artifact.size or null;
        _digest =
          if builtins.isString digest && builtins.match "sha256:[0-9a-f]{64}" digest != null then
            true
          else
            throw "Arbor Manager: ${context}.digest must be a sha256:<64-hex> content address.";
        _size =
          if size == null || (builtins.isInt size && size >= 0) then
            true
          else
            throw "Arbor Manager: ${context}.size must be a non-negative integer.";
      in
      assert _fields;
      assert _digest;
      assert _size;
      builtins.all (field: validatePublicValue "${context}.${field}" artifact.${field}) (
        builtins.attrNames artifact
      );

  validateSnapshot =
    validatePublicValue: context: snapshot:
    if !builtins.isAttrs snapshot then
      throw "Arbor Manager: ${context} must be an attribute set or null."
    else
      let
        required =
          field:
          if builtins.hasAttr field snapshot then
            snapshot.${field}
          else
            throw "Arbor Manager: ${context} is missing required field '${field}'.";
        format = required "format";
        version = required "version";
        facts = required "facts";
        _format =
          if builtins.isString format && format != "" then
            true
          else
            throw "Arbor Manager: ${context}.format must be a non-empty string.";
        _version =
          if builtins.isInt version && version > 0 then
            true
          else
            throw "Arbor Manager: ${context}.version must be a positive integer.";
        _facts =
          if builtins.isAttrs facts then
            true
          else
            throw "Arbor Manager: ${context}.facts must be an attribute set.";
      in
      assert _format;
      assert _version;
      assert _facts;
      validatePublicValue context snapshot;

  validateHardware =
    validatePublicValue: context: hardware:
    if hardware == null then
      true
    else if !builtins.isAttrs hardware then
      throw "Arbor Manager: ${context} must be an attribute set or null."
    else if builtins.hasAttr "modules" hardware then
      throw "Arbor Manager: ${context}.modules is not accepted; provide executable modules through the local source."
    else
      let
        snapshot = hardware.snapshot or null;
        artifact = hardware.artifact or null;
        _choice =
          if snapshot != null && artifact != null then
            throw "Arbor Manager: ${context} must provide either snapshot metadata or an artifact reference, not both."
          else if snapshot == null && artifact == null then
            throw "Arbor Manager: ${context} requires snapshot metadata or an artifact reference."
          else
            true;
      in
      assert _choice;
      if snapshot != null then
        validateSnapshot validatePublicValue "${context}.snapshot" snapshot
      else
        validateArtifact validatePublicValue "${context}.artifact" artifact;
in
{
  inherit validateHardware;
}
