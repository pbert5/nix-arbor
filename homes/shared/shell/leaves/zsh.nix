{ config, ... }:
{
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
        "colored-man-pages"
        "command-not-found"
        "dirhistory"
        "extract"
        "git"
        "sudo"
      ];
    };

    initContent = ''
      # Keep completion matching forgiving without making it ambiguous.
      zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
      zstyle ':completion:*' menu select
    '';
  };
}
