{ ... }:
{
  programs.starship = {
    enable = true;
    enableFishIntegration = false;
    settings = {
      add_newline = false;
      format = "$hostname$directory$git_branch$git_status$nix_shell$cmd_duration$status$line_break$character";

      character = {
        success_symbol = "[>](bold green) ";
        error_symbol = "[>](bold red) ";
      };

      directory = {
        truncation_length = 4;
        truncate_to_repo = false;
      };

      hostname = {
        ssh_only = true;
        trim_at = ".";
        format = "[$hostname](bold yellow) ";
      };

      git_branch.format = "[$symbol$branch]($style) ";
      git_status.format = "([$all_status$ahead_behind]($style) )";

      nix_shell = {
        format = "[nix:$name](bold blue) ";
        impure_msg = "impure";
        pure_msg = "pure";
        unknown_msg = "shell";
      };

      cmd_duration = {
        min_time = 1500;
        format = "[took $duration](dimmed yellow) ";
      };

      status = {
        disabled = false;
        format = "[$status]($style) ";
      };
    };
  };
}
