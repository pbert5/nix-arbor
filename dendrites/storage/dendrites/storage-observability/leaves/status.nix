{ pkgs, lib, site, hostInventory, ... }:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  hotCfg = lib.attrByPath [ "seaweedfs" "hotPool" ] { } fabric;
  repoRoot = annexCfg.repoRoot or "/srv/annex/cluster-data";
  hotMount = hotCfg.mountPoint or "/hot";
  numCopies = toString (annexCfg.defaultNumCopies or 2);
  masterPort = hotCfg.masterPort or 9333;
  filerPort = hotCfg.filerPort or 8888;

  hasAnnex = builtins.any
    (r: builtins.elem r (hostInventory.roles or [ ]))
    [ "annex-storage" "annex-client" "annex-workstation" "annex-compute-cache" ];
  hasSeaweedfs = builtins.any
    (r: builtins.elem r (hostInventory.roles or [ ]))
    [ "seaweed-master" "seaweed-volume" "seaweed-filer" ];
  hasRadicle = builtins.elem "radicle-seed" (hostInventory.roles or [ ]);

  fabricStatus = pkgs.writeShellApplication {
    name = "fabric-status";
    runtimeInputs = with pkgs; [ git git-annex curl coreutils ];
    text = ''
      set -euo pipefail
      OK=0
      WARN=0
      FAIL=0

      pass()  { echo "  [OK]   $*"; }
      warn()  { echo "  [WARN] $*"; WARN=$((WARN+1)); }
      fail()  { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }

      echo "=== Storage Fabric Status ==="
      echo ""

      ${lib.optionalString hasAnnex ''
        echo "--- git-annex ---"
        if [ -d "${repoRoot}/.git" ]; then
          pass "repo present at ${repoRoot}"
          UNSAFE=$(git -C "${repoRoot}" annex find --lackingcopies=1 2>/dev/null | wc -l || echo "?")
          if [ "$UNSAFE" = "0" ]; then
            pass "all files have >= ${numCopies} copies"
          else
            warn "$UNSAFE file(s) with fewer than ${numCopies} copies"
          fi
          REMOTES=$(git -C "${repoRoot}" remote | wc -l)
          if [ "$REMOTES" -gt 0 ]; then
            pass "$REMOTES remote(s) configured"
          else
            warn "no remotes configured — add peers with: cluster-annex add-remote <name> <host-alias>"
          fi
          KEYFILE="${repoRoot}/.ssh/id_ed25519"
          if [ -f "$KEYFILE" ]; then
            pass "annex SSH key present"
          else
            warn "annex SSH key missing (run: systemctl start annex-keygen)"
          fi
        else
          fail "annex repo NOT initialized — run: cluster-annex init"
        fi
        echo ""
      ''}

      ${lib.optionalString hasSeaweedfs ''
        echo "--- SeaweedFS ---"
        if systemctl is-active --quiet seaweedfs-master 2>/dev/null; then
          pass "seaweedfs-master active"
        else
          fail "seaweedfs-master not active"
        fi
        if systemctl is-active --quiet seaweedfs-volume 2>/dev/null; then
          pass "seaweedfs-volume active"
        else
          warn "seaweedfs-volume not active"
        fi
        if systemctl is-active --quiet seaweedfs-filer 2>/dev/null; then
          pass "seaweedfs-filer active"
        else
          warn "seaweedfs-filer not active"
        fi
        if mountpoint -q "${hotMount}" 2>/dev/null; then
          pass "hot pool mounted at ${hotMount}"
          df -h "${hotMount}" | tail -1 | awk '{print "         " $5 " used (" $3 "/" $2 ")"}'
        else
          warn "hot pool not mounted at ${hotMount} (access it to trigger automount)"
        fi
        echo ""
      ''}

      ${lib.optionalString hasRadicle ''
        echo "--- Radicle ---"
        if systemctl is-active --quiet radicle-seed 2>/dev/null; then
          pass "radicle-seed active"
        else
          fail "radicle-seed not active"
        fi
        echo ""
      ''}

      echo "--- Summary ---"
      echo "  OK: $OK  WARN: $WARN  FAIL: $FAIL"
      if [ "$FAIL" -gt 0 ]; then
        exit 1
      fi
    '';
  };
in
{
  environment.systemPackages = [ fabricStatus ];
}
