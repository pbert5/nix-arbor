{ lib, site, ... }:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  annexUser = annexCfg.user or "annex";
  annexGroup = annexCfg.group or "annex";
in
{
  users.groups.${annexGroup} = { };

  users.users.${annexUser} = {
    isSystemUser = true;
    group = annexGroup;
    description = "git-annex transfer service account";
    home = annexCfg.repoRoot or "/srv/annex/cluster-data";
    createHome = false;
    shell = "/bin/sh";
    # SSH authorized keys are managed by leaves/ssh.nix.
    openssh.authorizedKeys.keys = lib.mkDefault [ ];
  };
}
