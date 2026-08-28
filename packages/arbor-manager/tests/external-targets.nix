{ lib }:
let
  manager = import ../lib { inherit lib; };
  merged = manager.externalTargetMerge {
    static = {
      backup = {
        host = "backup.example";
        user = "root";
        provenance = {
          kind = "checked-in";
        };
      };
      gateway = {
        host = "gateway.example";
      };
    };
    local = [
      {
        name = "backup";
        record = {
          port = 2222;
        };
        provenance = {
          kind = "local";
          file = "targets.nix";
        };
      }
    ];
    session = [
      {
        name = "gateway";
        record = {
          user = "operator";
        };
        provenance = {
          kind = "session";
        };
      }
    ];
  };
  invalid = builtins.tryEval (
    builtins.deepSeq (manager.externalTargetMerge {
      static = [
        {
          name = "missing-host";
          record = { };
        }
      ];
    }) true
  );
in
assert
  builtins.attrNames merged.targetRecords == [
    "backup"
    "gateway"
  ];
assert merged.targetRecords.backup.host == "backup.example";
assert merged.targetRecords.backup.port == 2222;
assert merged.targetRecords.gateway.user == "operator";
assert merged.targets.backup.provenance.kind == "external-target-merge";
assert builtins.length merged.targets.backup.provenance.layers == 2;
assert !invalid.success;
true
