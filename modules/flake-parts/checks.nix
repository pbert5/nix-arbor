{
  config,
  inputs,
  lib,
  ...
}:
let
  exportedHostNames = builtins.attrNames (lib.filterAttrs (_: host: host.exported or true) config.dendritic.inventory.hosts);
  hostBootstrap = config.dendritic.inventory.hostBootstrap or { };
  colmenaNodes = builtins.removeAttrs config.flake.colmena [ "meta" ];
  deploymentTargetsHold =
    assert builtins.attrNames colmenaNodes == exportedHostNames;
    assert builtins.attrNames config.flake.deploy.nodes == exportedHostNames;
    assert lib.all (hostName: (colmenaNodes.${hostName}.deployment.targetHost or null) != null) exportedHostNames;
    assert lib.all (hostName: (config.flake.deploy.nodes.${hostName}.hostname or null) != null) exportedHostNames;
    assert (
      # For privateYggdrasil transport, the deploy-rs hostname must be the
      # logical host name (not the raw Ygg IPv6 address) so that the
      # operator's HM-managed SSH config handles address resolution,
      # identity selection, and user mapping transparently.
      let
        r640Transport = lib.attrByPath [ "r640-0" "deploymentTransport" ] "bootstrap" hostBootstrap;
        r640Target = config.flake.deploy.nodes."r640-0".hostname or null;
      in
      if r640Transport == "privateYggdrasil" then
        r640Target == "r640-0"
      else
        true
    );
    true;
in
{
  perSystem =
    { pkgs, system, ... }:
    let
      repoPackages = import ../../packages/packages.nix { inherit pkgs; };
    in
    {
      checks =
        {
          no-default-nix = import ../../checks/no-default-nix.nix {
            inherit pkgs;
          };

          network-overlay-eval = import ../../checks/network-overlay-eval.nix {
            inherit pkgs;
          };

          yggdrasil-private-smoke = import ../../checks/yggdrasil-private-smoke.nix {
            inherit pkgs;
          };

          deployment-targets-eval =
            assert deploymentTargetsHold;
            pkgs.runCommand "deployment-targets-eval" { } ''
              touch "$out"
            '';

          yggdrasil-bootstrap-help = pkgs.runCommand "yggdrasil-bootstrap-help" { nativeBuildInputs = [ repoPackages.yggdrasil-bootstrap ]; } ''
            yggdrasil-bootstrap --help > "$out"
          '';

          public-export-help = pkgs.runCommand "public-export-help" { nativeBuildInputs = [ repoPackages.public-export ]; } ''
            public-export --help > "$out"
          '';
        }
        // lib.optionalAttrs (builtins.hasAttr system inputs.deploy-rs.lib) (inputs.deploy-rs.lib.${system}.deployChecks config.flake.deploy);
    };
}
