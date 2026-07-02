{
  inputs,
  lib,
  pkgs,
  site,
  hostInventory,
  ...
}:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  repoRoot = annexCfg.repoRoot or "/srv/annex/cluster-data";
  annexUser = annexCfg.user or "annex";
  annexGroup = annexCfg.group or "annex";
  fabricOrg = lib.attrByPath [ "org" "storage" "annex" "fabric" ] { } hostInventory;

  isStorage = fabricOrg.storage or false;
  isClient = fabricOrg.client or false;
  isWorkstation = fabricOrg.workstation or false;
  isComputeCache = fabricOrg.computeCache or false;
  hasAnnexRepo = isStorage || isClient || isWorkstation || isComputeCache;

  unstablePkgs = import inputs.nixpkgs-unstable {
    inherit (pkgs.stdenv.hostPlatform) system;
    config.allowUnfree = true;
  };
  dumbpipe = unstablePkgs.dumbpipe;

  gitAnnexP2PIrohSrc = pkgs.fetchurl {
    url = "https://git-annex.branchable.com/special_remotes/p2p/git-annex-p2p-iroh";
    hash = "sha256-/d37Qvf+pLWQdryA3AaSeX5XxxLXNIg6Bw1ajID5fKU=";
  };

  gitAnnexP2PIroh = pkgs.writeShellApplication {
    name = "git-annex-p2p-iroh";
    runtimeInputs = [
      pkgs.git
      pkgs.gnupg
      dumbpipe
    ];
    text = ''
      exec ${lib.getExe pkgs.dash} ${gitAnnexP2PIrohSrc} "$@"
    '';
  };

  gitAnnexTorSudoPath = pkgs.symlinkJoin {
    name = "git-annex-tor-sudo-path";
    paths = [
      pkgs.git
      pkgs.systemd
      (pkgs.writeShellScriptBin "sudo" ''
        exec /run/wrappers/bin/sudo --preserve-env=PATH "$@"
      '')
    ];
  };

  gitAnnexP2PWrapper = pkgs.writeShellApplication {
    name = "git-annex";
    text = ''
      real_git_annex=${lib.getExe pkgs.git-annex}

      if [ "$#" -ge 1 ] && [ "$1" = "assistant-safety-info" ]; then
        cat <<'EOF'
      git-annex assistant is intentionally disabled by this flake.

      Why this is guarded:

      - The assistant is a long-running automatic sync process.
      - It can transfer annex content without another confirmation prompt.
      - It follows repository wanted/required content, remotes, and numcopies.
      - If those settings are incomplete or too broad, it can fill a disk.

      Before enabling it, check the target repository:

        git annex wanted here
        git annex required here
        git annex numcopies
        git annex remotes
        git remote -v
        df -h .

      If you have verified the repo policy and disk space, run:

        GIT_ANNEX_ALLOW_ASSISTANT=1 git-annex assistant

      Prefer cluster-annex and the explicit fabric services for normal storage
      fabric operation. Use the assistant only when you really want its automatic
      desktop sync behavior.
      EOF
        exit 0
      fi

      if [ "$#" -ge 1 ] && [ "$1" = "assistant" ] && [ "''${GIT_ANNEX_ALLOW_ASSISTANT:-}" != 1 ]; then
        cat >&2 <<'EOF'
      Refusing to start git-annex assistant.

      This is intentional. The assistant is an automatic sync process and can
      transfer annex content based on repository policy. If wanted content,
      required content, remotes, numcopies, or disk space are not exactly what you
      expect, it can move much more data than intended.

      This command is blocked by default to prevent accidental file sync and disk
      fill events.

      For the checklist and the explicit opt-in command, run:

        git-annex assistant-safety-info
      EOF
        exit 1
      fi

      if [ "$#" -ge 3 ] && [ "$1" = "p2p" ] && [ "$2" = "--enable" ] && [ "$3" = "tor" ]; then
        exec env -u DISPLAY PATH="${gitAnnexTorSudoPath}/bin" "$real_git_annex" "$@"
      fi

      if [ "$#" -ge 1 ] && [ "$1" = "enable-tor" ]; then
        exec env -u DISPLAY PATH="${gitAnnexTorSudoPath}/bin" "$real_git_annex" "$@"
      fi

      exec "$real_git_annex" "$@"
    '';
  };
in
{
  environment.systemPackages = with pkgs; [
    dumbpipe
    gitAnnexP2PIroh
    (lib.hiPrio gitAnnexP2PWrapper)
    gnupg
    magic-wormhole
    tor
    torsocks
  ];

  services.tor = {
    enable = true;
    client.enable = true;

    # Compatibility surface for `git annex p2p --enable tor`.
    # NixOS normally runs tor with a generated torrc in /nix/store, while
    # git-annex discovers and mutates /etc/tor/torrc.
    settings."%include" = "/etc/tor/torrc";
  };

  systemd.tmpfiles.rules = [
    "d /etc/tor 0755 root root - -"
    "f /etc/tor/torrc 0644 root root - -"
    "d /var/lib/tor-annex 0755 root root - -"
  ];

  systemd.services.tor.serviceConfig.BindPaths = lib.mkAfter [ "/var/lib/tor-annex" ];

  systemd.services.annex-remotedaemon = lib.mkIf hasAnnexRepo {
    description = "git-annex P2P remote daemon";
    wantedBy = [ "multi-user.target" ];
    after = [
      "annex-init.service"
      "network-online.target"
      "tor.service"
    ];
    wants = [
      "network-online.target"
      "tor.service"
    ];
    requires = [ "annex-init.service" ];
    environment = {
      HOME = repoRoot;
    };
    path = [
      pkgs.git
      pkgs.git-annex
      gitAnnexP2PIroh
      dumbpipe
    ];
    serviceConfig = {
      Type = "simple";
      User = annexUser;
      Group = annexGroup;
      WorkingDirectory = repoRoot;
      ExecStart = "${lib.getExe pkgs.git-annex} remotedaemon --foreground";
      Restart = "on-failure";
      RestartSec = "30s";
    };
  };

  assertions = [
    {
      assertion = lib.versionAtLeast pkgs.git-annex.version "10.20251103";
      message = "git-annex P2P over Iroh requires git-annex 10.20251103 or newer.";
    }
    {
      assertion = lib.versionAtLeast dumbpipe.version "0.33.0";
      message = "git-annex P2P over Iroh requires dumbpipe 0.33.0 or newer.";
    }
  ];
}
