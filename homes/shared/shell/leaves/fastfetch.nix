{
  config,
  lib,
  pkgs,
  site,
  ...
}:
let
  hyfetchCommand = lib.getExe pkgs.hyfetch;
  clusterHosts = builtins.attrNames (
    lib.filterAttrs (_: host: host.exported or false) (site.hosts or { })
  );
  # Only operator-capable hosts (desktoptoodle, r640-0) have a root SSH
  # identity for the rest of the cluster; followers like t320-0 can't
  # authenticate to check `systemctl is-system-running` remotely, so they
  # fall back to a ping reachability check instead.
  isOperatorCapable =
    (site.hostBootstrap.${config.flakeTarget.hostName} or { }).operatorCapable or false;
  clusterStatus = pkgs.writeShellApplication {
    name = "cluster-system-status";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.iputils
      pkgs.openssh
      pkgs.systemd
    ];
    text = ''
      hosts=(${lib.escapeShellArgs clusterHosts})
      local_host="$(< /proc/sys/kernel/hostname)"
      operator_capable=${lib.boolToString isOperatorCapable}
      workdir="$(mktemp -d)"
      trap 'rm -rf "$workdir"' EXIT
      green=$'\033[38;2;166;227;161m'
      yellow=$'\033[38;2;249;226;175m'
      red=$'\033[38;2;243;139;168m'
      reset=$'\033[0m'

      query_host() {
        local host="$1"
        local state
        local result

        if [[ "$host" == "$local_host" ]]; then
          state="$(systemctl is-system-running 2>/dev/null)" || true
          result="''${state:-unknown}"
        elif [[ "$operator_capable" == "true" ]]; then
          if state="$(timeout 3 ssh -o BatchMode=yes -o ConnectTimeout=2 "$host" systemctl is-system-running 2>/dev/null)"; then
            result="''${state:-unknown}"
          elif [[ -n "$state" ]]; then
            result="$state"
          else
            result="unreachable"
          fi
        else
          local address
          address="$(ssh -G "$host" 2>/dev/null | awk '$1 == "hostname" { print $2; exit }')"
          if [[ -n "$address" ]] && timeout 3 ping -c1 -W2 "$address" &>/dev/null; then
            result="reachable"
          else
            result="unreachable"
          fi
        fi

        printf '%s\n' "$result" > "$workdir/$host"
      }

      for host in "''${hosts[@]}"; do
        query_host "$host" &
      done
      wait

      problems=()
      for host in "''${hosts[@]}"; do
        state="$(< "$workdir/$host")"
        case "$state" in
          running | reachable)
            ;;
          unreachable)
            problems+=("$red""cannot reach $host""$reset")
            ;;
          *)
            problems+=("$yellow""$host is $state""$reset")
            ;;
        esac
      done

      if (( ''${#problems[@]} == 0 )); then
        printf '%sall running%s\n' "$green" "$reset"
      else
        printf -v summary '%s; ' "''${problems[@]}"
        printf '%s\n' "''${summary%; }"
      fi
    '';
  };
in
{
  programs.fastfetch = {
    enable = true;
    settings = {
      logo = {
        type = "auto";
        source = "nixos";
        padding.right = 2;
      };
      display = {
        pipe = false;
        separator = "  ";
        color = {
          keys = "#5BCEFA";
          title = "#F5A9B8";
          separator = "#FFFFFF";
        };
      };
      modules = [
        "title"
        "separator"
        "os"
        "kernel"
        "wm"
        "shell"
        "terminal"
        "packages"
        "memory"
        "uptime"
        {
          type = "command";
          key = "Cluster";
          text = lib.getExe clusterStatus;
        }
      ];
    };
  };

  home.packages = [ pkgs.hyfetch ];

  xdg.configFile."hyfetch.json".text = builtins.toJSON {
    preset = "transgender";
    mode = "rgb";
    auto_detect_light_dark = false;
    light_dark = "dark";
    lightness = 0.65;
    color_align.mode = "horizontal";
    backend = "fastfetch";
    args = null;
    distro = null;
    pride_month_disable = true;
    custom_ascii_path = null;
    custom_presets = null;
  };

  programs.zsh.initContent = lib.mkAfter ''
    if [[ -o interactive && -t 1 && -z ''${INSIDE_EMACS-} && -z ''${FASTFETCH_DISABLE-} && -z ''${__ASH_FASTFETCH_SHOWN-} ]]; then
      __ASH_FASTFETCH_SHOWN=1
      ${hyfetchCommand}
    fi
  '';
}
