{ ... }:
{
  programs.fzf = {
    enable = true;
    enableFishIntegration = true;
    defaultCommand = "fd --type f --hidden --follow --exclude .git";
    fileWidgetCommand = "fd --type f --hidden --follow --exclude .git";
    changeDirWidgetCommand = "fd --type d --hidden --follow --exclude .git";
    defaultOptions = [
      "--height=45%"
      "--layout=reverse"
      "--border"
    ];
    historyWidgetOptions = [ "--exact" ];
  };
}
