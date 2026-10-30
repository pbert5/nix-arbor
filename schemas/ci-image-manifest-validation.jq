.schemaVersion == 1 and
.repository == $repo and
(keys - ["schemaVersion", "repository", "images"] | length == 0) and
(.images | type == "array" and length > 0 and length <= 32) and
([.images[].name] | all(.[]; type == "string" and test("^[a-z0-9][a-z0-9._-]*$"))) and
([.images[].name] | length == (unique | length)) and
([.images[]] | all(.[];
  ((keys - ["name", "context", "dockerfile", "platforms", "buildArgs"]) | length == 0) and
  (.context | type == "string" and length > 0) and
  (.context | test("(^/|(^|/)\\.\\.(/|$))") | not) and
  (.dockerfile | type == "string" and length > 0) and
  (.dockerfile | test("(^/|(^|/)\\.\\.(/|$))") | not) and
  (.platforms == ["linux/amd64"]) and
  ((.buildArgs // {}) | type == "object") and
  ([((.buildArgs // {}) | keys[])] | all(.[];
    test("^[A-Z][A-Z0-9_]*$") and
    (test("(^|_)(SECRET|TOKEN|PASSWORD|CREDENTIAL|KEY|AUTH|BEARER|PASSPHRASE|CERTIFICATE)($|_)") | not)
  )) and
  ([((.buildArgs // {}) | .[])] | all(.[]; type == "string" or type == "number" or type == "boolean"))
))
