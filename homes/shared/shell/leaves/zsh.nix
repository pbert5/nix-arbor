{ config, lib, pkgs, ... }:
{
  home.packages = [
    pkgs.carapace
    pkgs.pay-respects
    pkgs.imagemagick  # catimg plugin
    pkgs.chroma       # colorize plugin
    pkgs.lastpass-cli # lpass plugin
    pkgs.fortune      # hitchhiker fortunes (strfile)
  ];

  # The bundled hitchhiker plugin regenerates hitchhiker.dat next to its
  # source file on every shell start, but that file lives in the read-only
  # Nix store. Pre-build it in a writable location instead and drop the
  # plugin from oh-my-zsh.plugins below.
  home.activation.hitchhikerFortunes = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    fortDir="$HOME/.local/share/hitchhiker-fortunes"
    $DRY_RUN_CMD mkdir -p "$fortDir"
    $DRY_RUN_CMD cp -f "${pkgs.oh-my-zsh}/share/oh-my-zsh/plugins/hitchhiker/fortunes/hitchhiker" "$fortDir/hitchhiker"
    $DRY_RUN_CMD ${pkgs.fortune}/bin/strfile "$fortDir/hitchhiker" "$fortDir/hitchhiker.dat" >/dev/null
  '';

  programs.zsh = {
    enable = true;
    enableCompletion = true;
    autocd = true;
    defaultKeymap = "emacs";

    autosuggestion = {
      enable = true;
      strategy = [
        "history"
        "completion"
      ];
    };

    syntaxHighlighting.enable = true;
    historySubstringSearch.enable = true;

    history = {
      path = "${config.xdg.dataHome}/zsh/history";
      size = 100000;
      save = 100000;
      expireDuplicatesFirst = true;
      extended = true;
      ignoreAllDups = true;
      ignoreSpace = true;
      share = true;
    };

    oh-my-zsh = {
      enable = true;
      plugins = [
        "alias-finder"
        "catimg"
        "colored-man-pages"
        "colorize"
        "command-not-found"
        "conda"
        "copyfile"
        "copypath"
        "dirhistory"
        "docker"
        "docker-compose"
        "dotenv"
        "extract"
        "fancy-ctrl-z"
        "git"
        "git-auto-fetch"
        "gitignore"
        "helm"
        "ipfs"
        "lol"
        "lpass"
        "magic-enter"
        "man"
        "pip"
        "pipenv"
        "pj"
        "podman"
        "pylint"
        "python"
        "safe-paste"
        "sudo"
        "tmux"
        "web-search"
        "zbell"
      ];
    };

    initContent = ''
      export CARAPACE_BRIDGES='zsh,fish,bash,inshellisense'
      zstyle ':completion:*' format $'\e[2;37mCompleting %d\e[m'
      source <(${pkgs.carapace}/bin/carapace _carapace)
      eval "$(${pkgs.pay-respects}/bin/pay-respects zsh --alias fuck)"

      alias hitchhiker="fortune -a $HOME/.local/share/hitchhiker-fortunes"
      alias hitchhiker_cow="hitchhiker | cowthink"

      ZSH_COLORIZE_TOOL=chroma
      MAGIC_ENTER_GIT_COMMAND='navi'
      MAGIC_ENTER_OTHER_COMMAND='navi'
      ZBELL_DURATION=15
      PROJECT_PATHS=(~/dev ~/projects ~/flake)
    '';
  };
}
