{ ... }:
{
  programs.fish = {
    enable = true;
    preferAbbrs = true;
    interactiveShellInit = ''
          set -g fish_greeting

          # VS Code integrated terminal and fish+starship can conflict.
          # Only initialize starship outside VS Code.
          if not set -q TERM_PROGRAM; or test "$TERM_PROGRAM" != "vscode"
            starship init fish | source
          end
    '';

    functions = {
          __terminal_guide_header = {
            argumentNames = "title";
            body = ''
              if type -q gum
                gum style --border rounded --padding "0 1" --margin "1 0" --border-foreground 81 --bold "$title"
              else
                printf '\n%s\n\n' "$title"
              end
            '';
          };

          __terminal_guide_label = {
            argumentNames = "label";
            body = ''
              if type -q gum
                gum style --foreground 212 --bold "$label"
              else
                printf '%s\n' "$label"
              end
            '';
          };

          __terminal_guide_hint = {
            argumentNames = "text";
            body = ''
              if type -q gum
                gum style --faint "$text"
              else
                printf '%s\n' "$text"
              end
            '';
          };

          __terminal_guide_read_choice = {
            argumentNames = "prompt";
            body = ''
              set -l choice
              if read -n 1 -P "$prompt" choice
                printf '%s' "$choice"
                return 0
              end

              return $status
            '';
          };

          __terminal_guide_table = ''
            __terminal_guide_label "  #  Name           Call                   Use"
            printf '%s\n' \
              "  1  Fish           help, fish             shell basics and builtins" \
              "  2  Starship       prompt                 prompt context at a glance" \
              "  3  fzf            Ctrl+T Alt+C Ctrl+R    fuzzy files, dirs, history" \
              "  4  zoxide         z <dir>                jump to places you visit a lot" \
              "  5  atuin          atuin search           searchable shell history" \
              "  6  eza            ls ll la lt lla        better listings with git info" \
              "  7  yazi           y [path]               interactive file navigation" \
              "  8  zellij         zellij                 terminal multiplexer" \
              "  9  Repo helpers   ns nb nf               rebuild and flake shortcuts"
          '';

          __terminal_guide_topic = {
            argumentNames = "topic";
            body = ''
              while true
                clear

                set -l title
                set -l call
                set -l use
                set -l when_lines
                set -l try_lines
                set -l note_lines

                switch $topic
                  case 1
                    set title "Fish"
                    set call "help, fish"
                    set use "Your main interactive shell and builtin command language."
                    set when_lines \
                      "Use this when you need shell syntax, variables, loops, or a reminder of how fish behaves." \
                      "Typing 'help' with no topic opens this guide. Typing 'help string' still opens normal fish help."
                    set try_lines \
                      "help string" \
                      "help set" \
                      "fish_config"
                    set note_lines \
                      "Fish greeting is disabled to keep startup clean." \
                      "This shell is configured as the fish-first daily workflow."
                  case 2
                    set title "Starship"
                    set call "prompt"
                    set use "Compact prompt context without adding noise."
                    set when_lines \
                      "Use the prompt to quickly spot your current directory, git state, nix shell context, slow commands, and failed exits." \
                      "It is there to orient you before you type, not as a command you run directly."
                    set try_lines \
                      "cd $HOME" \
                      "git status" \
                      "false"
                    set note_lines \
                      "Starship init is skipped in VS Code terminals because that combo can be flaky." \
                      "You should still see it in normal terminals."
                  case 3
                    set title "fzf"
                    set call "Ctrl+T, Alt+C, Ctrl+R"
                    set use "Fuzzy file search, directory jumping, and history search."
                    set when_lines \
                      "Use Ctrl+T to find a file path fast." \
                      "Use Alt+C to fuzzy-pick a directory and jump there." \
                      "Use Ctrl+R to search command history instead of scrolling forever."
                    set try_lines \
                      "Press Ctrl+T in any directory to insert a file path." \
                      "Press Alt+C to jump to a subdirectory." \
                      "Press Ctrl+R to search previous commands."
                    set note_lines \
                      "Search uses fd, includes hidden files, and ignores .git." \
                      "The picker uses a reverse layout with a border."
                  case 4
                    set title "zoxide"
                    set call "z <dir>"
                    set use "Jump to directories you visit often by memory instead of full paths."
                    set when_lines \
                      "Use this when you know the project name but do not want to type or fuzzy-pick the whole path." \
                      "It gets better as you keep visiting the same places."
                    set try_lines \
                      "z flake" \
                      "z src" \
                      "z home"
                    set note_lines \
                      "Great for repeat travel." \
                      "Use fzf when you want to browse. Use zoxide when you already know the target."
                  case 5
                    set title "atuin"
                    set call "atuin search"
                    set use "Better shell history with fuzzy search."
                    set when_lines \
                      "Use this when you remember part of an old command but not the exact full line." \
                      "It is usually the right move for 'I did this once before, what was it?'"
                    set try_lines \
                      "atuin search nixos-rebuild" \
                      "atuin search zellij" \
                      "Press Ctrl+R for the integrated history search path."
                    set note_lines \
                      "History sync is off right now." \
                      "Search mode is fuzzy and update checks are disabled."
                  case 6
                    set title "eza"
                    set call "ls, ll, la, lt, lla"
                    set use "Cleaner listings with git status, icons, and better defaults."
                    set when_lines \
                      "Use plain ls for a quick directory view." \
                      "Use ll for a detailed list, la for hidden files, and lt when you care about tree-like structure."
                    set try_lines \
                      "ls" \
                      "ll" \
                      "la"
                    set note_lines \
                      "Listings group directories first and show a header row." \
                      "Git status is enabled when available."
                  case 7
                    set title "yazi"
                    set call "y [path]"
                    set use "Interactive file manager that can also change your shell directory."
                    set when_lines \
                      "Use this when you want to browse a project, inspect files, and move around visually." \
                      "It is stronger than ls when you are exploring instead of targeting a known file."
                    set try_lines \
                      "y" \
                      "y ~/src" \
                      "Open yazi, move around, then quit to land in the chosen directory."
                    set note_lines \
                      "The wrapper command is 'y'." \
                      "Exiting yazi updates your current shell directory."
                  case 8
                    set title "zellij"
                    set call "zellij"
                    set use "Terminal multiplexer for persistent panes and sessions."
                    set when_lines \
                      "Use this when one shell is not enough and you want splits, tabs, or a long-running workspace." \
                      "It helps when you want logs in one pane and editing or rebuilds in another."
                    set try_lines \
                      "zellij" \
                      "Open a new pane and keep a rebuild running while you work."
                    set note_lines \
                      "It is enabled as the current multiplexer choice." \
                      "This guide is about when to reach for it, not a full keybinding map."
                  case 9
                    set title "Repo helpers"
                    set call "ns, nb, nf"
                    set use "Shortcuts for common flake rebuild and inspection tasks."
                    set when_lines \
                      "Use ns to switch the machine to the configured flake target." \
                      "Use nb to build the configured system result without switching." \
                      "Use nf to inspect the configured flake outputs."
                    set try_lines \
                      "ns" \
                      "nb" \
                      "nf"
                    set note_lines \
                      "The repo helper abbreviations read their flake path and host target from Home Manager config." \
                      "Override those values per user when the flake checkout lives somewhere else."
                  case '*'
                    return 1
                end

                __terminal_guide_header "$title"
                __terminal_guide_label "Call"
                printf '  %s\n\n' "$call"
                __terminal_guide_label "Use"
                printf '  %s\n\n' "$use"
                __terminal_guide_label "When to Reach for It"
                for line in $when_lines
                  printf '  - %s\n' "$line"
                end
                printf '\n'
                __terminal_guide_label "Try"
                for line in $try_lines
                  printf '  %s\n' "$line"
                end
                printf '\n'
                __terminal_guide_label "Notes"
                for line in $note_lines
                  printf '  - %s\n' "$line"
                end
                printf '\n'
                __terminal_guide_hint "Press b to go back, q to quit."

                set -l choice (__terminal_guide_read_choice "> ")
                or return 0

                switch $choice
                  case b B
                    return 0
                  case q Q
                    exit 0
                end
              end
            '';
          };

          __terminal_guide_main = {
            body = ''
              while true
                clear
                __terminal_guide_header "Terminal Guide"
                __terminal_guide_hint "Press a number to learn a tool, or q to quit."
                printf '\n'
                __terminal_guide_table
                printf '\n'

                set -l choice (__terminal_guide_read_choice "> ")
                or return 0

                switch $choice
                  case 1 2 3 4 5 6 7 8 9
                    __terminal_guide_topic "$choice"
                  case q Q
                    return 0
                end
              end
            '';
          };

          help = {
            wraps = "help";
            body = ''
              if test (count $argv) -eq 0
                __terminal_guide_main
              else
                builtin help $argv
              end
            '';
          };

          why = {
            body = ''
              __terminal_guide_main
            '';
          };

          saveme = {
            body = ''
              __terminal_guide_main
            '';
          };

          save-me = {
            body = ''
              __terminal_guide_main
            '';
          };
    };
  };
}
