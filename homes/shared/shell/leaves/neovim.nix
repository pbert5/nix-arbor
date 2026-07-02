{ pkgs, ... }:
{
  home.packages = [ pkgs.lazygit ];

  home.sessionVariables = {
    EDITOR = "nvim";
    VISUAL = "nvim";
  };

  programs.neovim = {
    enable = true;
    defaultEditor = true;
    viAlias = true;
    vimAlias = true;
    withRuby = false;
    withPython3 = false;
    extraPackages = with pkgs; [
      gcc
      tree-sitter
    ];
    initLua = ''
      vim.opt.rtp:prepend("${pkgs.vimPlugins.lazy-nvim}")

      require("lazy").setup({
        spec = {
          { "LazyVim/LazyVim", import = "lazyvim.plugins" },
        },
        defaults = { lazy = false, version = false },
        install = { colorscheme = { "tokyonight", "habamax" } },
        checker = { enabled = true },
        performance = {
          rtp = {
            disabled_plugins = {
              "gzip", "tarPlugin", "tohtml", "tutor", "zipPlugin",
            },
          },
        },
      })
    '';
  };
}
