{ lib, pkgs, site, hostInventory, hostName, ... }:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  repoRoot = annexCfg.repoRoot or "/srv/annex/cluster-data";
  annexUser = annexCfg.user or "annex";
  annexGroup = annexCfg.group or "annex";
  annexSshDir = "${repoRoot}/.ssh";
  annexSshKey = "${annexSshDir}/id_ed25519";

  isStorage = builtins.elem "annex-storage" (hostInventory.roles or [ ]);
  isClient = builtins.elem "annex-client" (hostInventory.roles or [ ]);
  isWorkstation = builtins.elem "annex-workstation" (hostInventory.roles or [ ]);
  needsInit = isStorage || isClient || isWorkstation;

  # Preferred content group for this host (optional inventory setting).
  annexGroup_ = lib.attrByPath [ "org" "storage" "annex" "group" ] (
    if isStorage then "hot"
    else if isWorkstation then "workstation"
    else "transient"
  ) hostInventory;
  numCopies = toString (annexCfg.defaultNumCopies or 2);
in
lib.mkIf needsInit {
  # Generate an SSH keypair for the annex service account on first boot.
  # The public key path is ${annexSshKey}.pub — add it to peer host inventory
  # entries under org.storage.annex.sshPublicKey after the first activation.
  systemd.services.annex-keygen = {
    description = "Generate annex SSH identity keypair (first boot)";
    wantedBy = [ "multi-user.target" ];
    before = [ "annex-init.service" ];
    after = [ "systemd-tmpfiles-setup.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = annexUser;
      Group = annexGroup;
    };
    script = ''
      set -euo pipefail
      mkdir -p "${annexSshDir}"
      chmod 700 "${annexSshDir}"
      if [ ! -f "${annexSshKey}" ]; then
        ${lib.getExe' pkgs.openssh "ssh-keygen"} \
          -t ed25519 \
          -C "${hostName}-annex" \
          -N "" \
          -f "${annexSshKey}"
        echo "annex SSH key generated at ${annexSshKey}.pub"
      fi
    '';
  };

  # Initialize the git-annex repository on first boot.
  # Sets the preferred-content group and numcopies so every host self-describes
  # its role in the fabric from day one.
  systemd.services.annex-init = {
    description = "Initialize git-annex cluster-data repo (first boot)";
    wantedBy = [ "multi-user.target" ];
    after = [
      "systemd-tmpfiles-setup.service"
      "annex-keygen.service"
    ];
    requires = [ "annex-keygen.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = annexUser;
      Group = annexGroup;
    };
    environment = {
      HOME = repoRoot;
      GIT_AUTHOR_NAME = "${hostName}-annex";
      GIT_AUTHOR_EMAIL = "${hostName}-annex@local";
      GIT_COMMITTER_NAME = "${hostName}-annex";
      GIT_COMMITTER_EMAIL = "${hostName}-annex@local";
    };
    path = [ pkgs.git pkgs.git-annex ];
    script = ''
      set -euo pipefail
      cd "${repoRoot}"
      if [ ! -d ".git" ]; then
        git init
        git annex init "${hostName}-annex"
        git annex numcopies ${numCopies}
        git annex group here "${annexGroup_}"
        git annex wanted here groupwanted
        echo "annex repo initialized at ${repoRoot} (group: ${annexGroup_})"
      else
        # Ensure group/wanted is set even on re-activation.
        git annex group here "${annexGroup_}" 2>/dev/null || true
        git annex wanted here groupwanted 2>/dev/null || true
      fi
    '';
  };

  # Expose the annex public key as a well-known file so bootstrap tooling can
  # read it without knowing the exact path.
  systemd.tmpfiles.rules = [
    "d ${annexSshDir} 0700 ${annexUser} ${annexGroup} - -"
  ];
}
