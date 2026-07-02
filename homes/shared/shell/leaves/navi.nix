{
  dendritic ? {
    cheatsheets = [ ];
  },
  lib,
  pkgs,
  ...
}:
let
  cheatLinks = pkgs.linkFarm "dendritic-navi-cheats" (
    builtins.map (sheet: {
      inherit (sheet) name path;
    }) (dendritic.cheatsheets or [ ])
  );
  upstreamSources = {
    denisidoro = pkgs.fetchFromGitHub {
      owner = "denisidoro";
      repo = "cheats";
      rev = "1339965e9615ce00174cc308a41279d9c59aa75f";
      hash = "sha256-wPsAazAGKPhu0MZfZbZ0POUBEMg95frClAQERTDFXUg=";
    };
    kbknapp = pkgs.fetchFromGitHub {
      owner = "kbknapp";
      repo = "navi-cheats";
      rev = "80255ad3f66a17c111388d79748475d06a423666";
      hash = "sha256-9LSwCWyn/5QJ8TWMNOCtH5SMnlk3SOt11UaLbFXiG98=";
    };
    papanito = pkgs.fetchFromGitHub {
      owner = "papanito";
      repo = "cheats";
      rev = "89e8a4b34b8d793c5a18b5b726a6e35ba342f0b9";
      hash = "sha256-+UQaDOeb02fFTi/lbqYCdPcBKHlUGbNVOWxB7jReqmo=";
    };
  };
  curatedUpstreamCheats = pkgs.linkFarm "curated-navi-cheats" [
    {
      name = "atuin.cheat";
      path = "${upstreamSources.papanito}/atuin.cheat";
    }
    {
      name = "awk.cheat";
      path = "${upstreamSources.papanito}/utils/awk.cheat";
    }
    {
      name = "curl.cheat";
      path = "${upstreamSources.kbknapp}/cheats/curl.cheat";
    }
    {
      name = "docker.cheat";
      path = "${upstreamSources.kbknapp}/cheats/docker.cheat";
    }
    {
      name = "du.cheat";
      path = "${upstreamSources.papanito}/utils/du.cheat";
    }
    {
      name = "find.cheat";
      path = "${upstreamSources.papanito}/utils/find.cheat";
    }
    {
      name = "git.cheat";
      path = "${upstreamSources.kbknapp}/cheats/git.cheat";
    }
    {
      name = "gpg.cheat";
      path = "${upstreamSources.kbknapp}/cheats/gpg.cheat";
    }
    {
      name = "grep.cheat";
      path = "${upstreamSources.papanito}/utils/grep.cheat";
    }
    {
      name = "ip.cheat";
      path = "${upstreamSources.papanito}/utils/ip.cheat";
    }
    {
      name = "journalctl.cheat";
      path = "${upstreamSources.papanito}/utils/journalctl.cheat";
    }
    {
      name = "json.cheat";
      path = "${upstreamSources.denisidoro}/misc/json.cheat";
    }
    {
      name = "nix-env.cheat";
      path = "${upstreamSources.papanito}/nix/nix-env.cheat";
    }
    {
      name = "nix-flake.cheat";
      path = "${upstreamSources.papanito}/nix/nix_flake.cheat";
    }
    {
      name = "nixos.cheat";
      path = "${upstreamSources.papanito}/nix/nixos.cheat";
    }
    {
      name = "network.cheat";
      path = "${upstreamSources.kbknapp}/cheats/network.cheat";
    }
    {
      name = "nmap.cheat";
      path = "${upstreamSources.kbknapp}/cheats/nmap.cheat";
    }
    {
      name = "rust.cheat";
      path = "${upstreamSources.kbknapp}/cheats/rust.cheat";
    }
    {
      name = "sed.cheat";
      path = "${upstreamSources.papanito}/utils/sed.cheat";
    }
    {
      name = "ss.cheat";
      path = "${upstreamSources.kbknapp}/cheats/ss.cheat";
    }
    {
      name = "ssh.cheat";
      path = "${upstreamSources.kbknapp}/cheats/ssh.cheat";
    }
    {
      name = "strace.cheat";
      path = "${upstreamSources.kbknapp}/cheats/strace.cheat";
    }
    {
      name = "systemctl.cheat";
      path = "${upstreamSources.kbknapp}/cheats/systemctl.cheat";
    }
    {
      name = "tar.cheat";
      path = "${upstreamSources.papanito}/utils/tar.cheat";
    }
    {
      name = "tmux.cheat";
      path = "${upstreamSources.kbknapp}/cheats/tmux.cheat";
    }
  ];
in
{
  home.packages = [ pkgs.navi ];

  xdg.dataFile = {
    "navi/cheats/dendritic".source = cheatLinks;
    "navi/cheats/upstream".source = curatedUpstreamCheats;
  };

  programs.zsh.initContent = lib.mkAfter ''
    if command -v navi >/dev/null 2>&1; then
      eval "$(navi widget zsh)"

      _navi_magic_accept_line() {
        if [[ -z "$BUFFER" && "$CONTEXT" = start ]]; then
          local replacement
          replacement="$(navi --print </dev/tty)" || {
            zle redisplay
            return 0
          }

          if [[ -n "$replacement" ]]; then
            BUFFER="$replacement"
            CURSOR=''${#BUFFER}
            zle _navi_magic_orig_accept_line -- "$@"
            return
          fi

          zle redisplay
          return 0
        fi

        zle _navi_magic_orig_accept_line -- "$@"
      }

      if [[ "$widgets[accept-line]" != user:_navi_magic_accept_line ]]; then
        case "$widgets[accept-line]" in
          user:*) zle -N _navi_magic_orig_accept_line "''${widgets[accept-line]#user:}" ;;
          builtin) zle -N _navi_magic_orig_accept_line .accept-line ;;
        esac

        zle -N accept-line _navi_magic_accept_line
      fi
    fi

    clusterctl() {
      if [ "$#" -eq 0 ]; then
        navi --tag-rules clusterctl
        return
      fi

      command clusterctl "$@"
    }
  '';
}
