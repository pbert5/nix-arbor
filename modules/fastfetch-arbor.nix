args@{
  lib,
  pkgs,
  ...
}:
let
  machine = lib.attrByPath [ "arbor" "machine" "hostname" ] null (args.osConfig or { });
  status = pkgs.writeShellApplication {
    name = "arbor-fastfetch-status";
    runtimeInputs = with pkgs; [
      coreutils
      curl
      jq
      systemd
    ];
    text = builtins.readFile ./fastfetch-status.sh;
  };
in
{
  programs.fastfetch.settings.modules = lib.mkAfter [
    {
      type = "command";
      key = "Arbor Registry";
      text = "${lib.getExe status} registry";
    }
    {
      type = "command";
      key = "Arbor Manager";
      text = "${lib.getExe status} manager ${
        lib.escapeShellArg (
          if machine == null then "configuration unknown" else "managed machine: ${machine}"
        )
      }";
    }
    {
      type = "command";
      key = "OpenBao (localhost)";
      text = "${lib.getExe status} openbao";
    }
  ];
}
