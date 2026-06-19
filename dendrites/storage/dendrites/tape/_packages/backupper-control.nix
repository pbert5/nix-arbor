{ pkgs }:

pkgs.writeShellApplication {
  name = "backupper";
  runtimeInputs = [
    pkgs.coreutils
    pkgs.findutils
    pkgs.gnused
    pkgs.systemd
  ];
  text = ''
    set -eu

    plan_root="/etc/backupper/plans"

    list_plans() {
      if [ ! -d "$plan_root" ]; then
        return 0
      fi

      find "$plan_root" -maxdepth 1 -name '*.json' -printf '%f\n' \
        | sed 's/\.json$//' \
        | sort
    }

    collect_targets() {
      if [ "$#" -gt 0 ]; then
        printf '%s\n' "$@"
        return 0
      fi

      list_plans
    }

    if [ "$#" -lt 1 ]; then
      echo "usage: backupper <list|start|resume|stop|restart|status|logs> [plan ...]" >&2
      exit 2
    fi

    command="$1"
    shift

    case "$command" in
      list)
        list_plans
        ;;
      resume)
        targets="$(collect_targets "$@")"
        if [ -z "$targets" ]; then
          echo "No local backupper plans were found under $plan_root." >&2
          exit 1
        fi
        printf '%s\n' "$targets" | while IFS= read -r plan; do
          [ -n "$plan" ] || continue
          systemd-run \
            --unit "backupper-resume-$plan" \
            --collect \
            --property StandardOutput=journal \
            --property StandardError=journal \
            /run/current-system/sw/bin/backupper-runner \
            --config "$plan_root/$plan.json"
        done
        ;;
      start|stop|restart)
        targets="$(collect_targets "$@")"
        if [ -z "$targets" ]; then
          echo "No local backupper plans were found under $plan_root." >&2
          exit 1
        fi
        printf '%s\n' "$targets" | while IFS= read -r plan; do
          [ -n "$plan" ] || continue
          systemctl "$command" "backupper-$plan.service"
        done
        ;;
      status)
        targets="$(collect_targets "$@")"
        if [ -z "$targets" ]; then
          echo "No local backupper plans were found under $plan_root." >&2
          exit 1
        fi
        printf '%s\n' "$targets" | while IFS= read -r plan; do
          [ -n "$plan" ] || continue
          systemctl --no-pager --full status "backupper-$plan.service"
        done
        ;;
      logs)
        targets="$(collect_targets "$@")"
        if [ -z "$targets" ]; then
          echo "No local backupper plans were found under $plan_root." >&2
          exit 1
        fi
        printf '%s\n' "$targets" | while IFS= read -r plan; do
          [ -n "$plan" ] || continue
          journalctl -u "backupper-$plan.service" --no-pager
        done
        ;;
      *)
        echo "unknown command: $command" >&2
        exit 2
        ;;
    esac
  '';
}
