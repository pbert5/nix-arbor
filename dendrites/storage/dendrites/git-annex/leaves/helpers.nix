{ pkgs, lib, site, hostInventory, ... }:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  hotCfg = lib.attrByPath [ "seaweedfs" "hotPool" ] { } fabric;
  repoRoot = annexCfg.repoRoot or "/srv/annex/cluster-data";
  annexUser = annexCfg.user or "annex";
  hotMount = hotCfg.mountPoint or "/hot";
  numCopies = toString (annexCfg.defaultNumCopies or 2);

  # Discover private Ygg remotes for add-remote guidance.
  privateYggNodes = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" ] { } site;
  yggRemoteLines = lib.concatStringsSep "\n" (
    lib.mapAttrsToList (name: node:
      let alias = lib.head (node.aliases or [ name ]);
      in "  ${name}: annex+ssh://${alias}${repoRoot}"
    ) (lib.filterAttrs (n: _: n != (hostInventory.hostName or "")) privateYggNodes)
  );

  clusterAnnex = pkgs.writeShellApplication {
    name = "cluster-annex";
    runtimeInputs = with pkgs; [ git git-annex rsync coreutils ];
    text = ''
      set -euo pipefail
      ANNEX_ROOT="${repoRoot}"
      HOT_MOUNT="${hotMount}"
      CMD="''${1:-help}"
      shift || true

      case "$CMD" in

        # ── Initialization ────────────────────────────────────────────────
        init)
          cd "$ANNEX_ROOT"
          if [ ! -d ".git" ]; then
            git init
            git annex init "$(hostname)-annex"
            git annex numcopies ${numCopies}
            echo "annex repo initialized — set group and add remotes with 'cluster-annex set-group' and 'cluster-annex add-remote'"
          else
            echo "annex already initialized at $ANNEX_ROOT"
          fi
          ;;

        set-group)
          GROUP="''${1:?Usage: cluster-annex set-group <group>}"
          cd "$ANNEX_ROOT"
          git annex group here "$GROUP"
          git annex wanted here groupwanted
          echo "group set to $GROUP"
          ;;

        add-remote)
          # Usage: cluster-annex add-remote <name> <host-alias>
          # e.g.:  cluster-annex add-remote r640-0 r640-0-ygg
          NAME="''${1:?Usage: cluster-annex add-remote <name> <host-alias>}"
          HOST="''${2:?Usage: cluster-annex add-remote <name> <host-alias>}"
          cd "$ANNEX_ROOT"
          git remote add "$NAME" "annex+ssh://$HOST$ANNEX_ROOT"
          git annex sync "$NAME"
          echo "remote '$NAME' added and synced"
          ;;

        # ── Content operations ────────────────────────────────────────────
        get-active)
          PROJECT="''${1:?Usage: cluster-annex get-active <project>}"
          git -C "$ANNEX_ROOT" annex get "projects/$PROJECT/" --from=here
          ;;

        sync)
          git -C "$ANNEX_ROOT" annex sync --jobs=4 "''${@}"
          ;;

        sync-all)
          git -C "$ANNEX_ROOT" annex sync --content --jobs=4
          ;;

        whereis)
          git -C "$ANNEX_ROOT" annex whereis "''${1:-.}"
          ;;

        drop-safe)
          TARGET="''${1:?Usage: cluster-annex drop-safe <path>}"
          git -C "$ANNEX_ROOT" annex drop "$TARGET" --auto
          ;;

        archive)
          PATH_ARG="''${1:?Usage: cluster-annex archive <path>}"
          git -C "$ANNEX_ROOT" annex copy "$PATH_ARG" --to=archive --jobs=4
          ;;

        fsck-important)
          git -C "$ANNEX_ROOT" annex fsck \
            --from=here --jobs=4 \
            --include="*.important"
          ;;

        # ── M8: SeaweedFS /hot staging ────────────────────────────────────
        # Pull annex content into the hot pool's staging area under /hot.
        # The hot pool is a working area, not the source of truth — the annex
        # repo tracks identity and copy policy.
        stage)
          PROJECT="''${1:?Usage: cluster-annex stage <project>}"
          DEST="$HOT_MOUNT/projects/$PROJECT"
          mkdir -p "$DEST"
          git -C "$ANNEX_ROOT" annex get "projects/$PROJECT/" --jobs=4
          rsync -a --copy-links "$ANNEX_ROOT/projects/$PROJECT/" "$DEST/"
          echo "Staged $PROJECT to $DEST"
          ;;

        unstage)
          PROJECT="''${1:?Usage: cluster-annex unstage <project>}"
          DEST="$HOT_MOUNT/projects/$PROJECT"
          if [ -d "$DEST" ]; then
            rm -rf "$DEST"
            echo "Unstaged $DEST"
          else
            echo "Nothing staged at $DEST"
          fi
          ;;

        # ── M9: Job workflow ──────────────────────────────────────────────
        job-stage)
          # Fetch project inputs into /hot ready for compute.
          PROJECT="''${1:?Usage: cluster-annex job-stage <project> <job-id>}"
          JOB="''${2:?Usage: cluster-annex job-stage <project> <job-id>}"
          DEST="$HOT_MOUNT/scratch/$JOB"
          mkdir -p "$DEST"
          git -C "$ANNEX_ROOT" annex get "projects/$PROJECT/" --jobs=4
          rsync -a --copy-links "$ANNEX_ROOT/projects/$PROJECT/" "$DEST/input/"
          mkdir -p "$DEST/output"
          echo "Job $JOB staged from project $PROJECT at $DEST"
          ;;

        job-publish)
          # Annex-add outputs from a completed job and sync to peers.
          JOB="''${1:?Usage: cluster-annex job-publish <job-id>}"
          SRC="$HOT_MOUNT/scratch/$JOB/output"
          DEST="$ANNEX_ROOT/outputs/$JOB"
          if [ ! -d "$SRC" ]; then
            echo "No output directory found at $SRC" >&2
            exit 1
          fi
          mkdir -p "$DEST"
          rsync -a "$SRC/" "$DEST/"
          git -C "$ANNEX_ROOT" annex add "outputs/$JOB/"
          git -C "$ANNEX_ROOT" -c user.name="$(hostname)-annex" \
            -c user.email="$(hostname)-annex@local" \
            commit -m "outputs: publish job $JOB" || true
          git -C "$ANNEX_ROOT" annex sync --content --jobs=4
          echo "Job $JOB outputs published to annex"
          ;;

        job-clean)
          # Remove hot staging for a job after publish.
          JOB="''${1:?Usage: cluster-annex job-clean <job-id>}"
          DEST="$HOT_MOUNT/scratch/$JOB"
          if [ -d "$DEST" ]; then
            rm -rf "$DEST"
            echo "Cleaned $DEST"
          fi
          # Drop from hot pool if policy allows (numcopies check).
          git -C "$ANNEX_ROOT" annex drop "outputs/$JOB/" --auto 2>/dev/null || true
          ;;

        # ── M13: Observability status ─────────────────────────────────────
        status)
          echo "=== cluster-annex status ==="
          echo ""
          echo "--- annex repo ---"
          git -C "$ANNEX_ROOT" annex info --fast 2>/dev/null || echo "  (not initialized)"
          echo ""
          echo "--- copy safety check (files with < ${numCopies} copies) ---"
          git -C "$ANNEX_ROOT" annex find --lackingcopies=1 2>/dev/null \
            | head -20 || echo "  (could not check)"
          echo ""
          echo "--- remotes ---"
          git -C "$ANNEX_ROOT" remote -v 2>/dev/null || echo "  (no remotes)"
          if [ -d "$HOT_MOUNT" ]; then
            echo ""
            echo "--- hot pool ($HOT_MOUNT) ---"
            df -h "$HOT_MOUNT" 2>/dev/null || echo "  (not mounted)"
          fi
          ;;

        help|*)
          echo "cluster-annex <command> [args]"
          echo ""
          echo "Initialization:"
          echo "  init                           initialize annex on this host"
          echo "  set-group <group>              set preferred-content group"
          echo "  add-remote <name> <host-alias> add a peer remote over Ygg"
          echo ""
          echo "Content:"
          echo "  get-active <project>           fetch active project files"
          echo "  sync [remote]                  sync metadata with peers"
          echo "  sync-all                       sync metadata + content"
          echo "  whereis [path]                 show copy locations"
          echo "  drop-safe <path>               drop if policy allows"
          echo "  archive <path>                 copy path to archive remotes"
          echo "  fsck-important                 fsck files tagged important"
          echo ""
          echo "Hot pool staging (M8):"
          echo "  stage <project>                copy project into /hot"
          echo "  unstage <project>              remove staged project from /hot"
          echo ""
          echo "Job workflow (M9):"
          echo "  job-stage <project> <job-id>   stage inputs for a compute job"
          echo "  job-publish <job-id>           annex-add outputs and sync"
          echo "  job-clean <job-id>             clean hot staging after publish"
          echo ""
          echo "Observability (M13):"
          echo "  status                         show annex and hot pool health"
          echo ""
          echo "Ygg remotes available:"
          ${if yggRemoteLines != "" then ''echo "${yggRemoteLines}"'' else ''echo "  (none configured)"''}
          ;;
      esac
    '';
  };
in
{
  environment.systemPackages = [ clusterAnnex ];
}

