{
  config,
  lib,
  pkgs,
  ...
}:
let
  wallpaperRoot = "${config.home.homeDirectory}/Pictures/Wallpapers";
  awww = lib.getExe pkgs.awww;
  rofi = lib.getExe pkgs.rofi;

  hydrusWallpapers = pkgs.writers.writePython3Bin "hydrus-wallpapers" { } ''
    import json
    import os
    import pathlib
    import shutil
    import ssl
    import sys
    import tempfile
    import urllib.error
    import urllib.parse
    import urllib.request

    API_URL = os.environ.get("HYDRUS_API_URL", "https://127.0.0.1:45869")
    CONFIG_HOME = pathlib.Path(
        os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")
    )
    KEY_FILE = pathlib.Path(
        os.environ.get(
            "HYDRUS_KEY_FILE",
            CONFIG_HOME / "hydrus-watcher-tagger" / "access_key",
        )
    )
    IMAGE_PREDICATE = "system:filetype = image/jpg, image/png, image/webp"
    RATING_PREDICATE = "system:rating for wallpaper is like"

    TLS_CONTEXT = ssl.create_default_context()
    if os.environ.get("HYDRUS_TLS_VERIFY", "0") != "1":
        TLS_CONTEXT.check_hostname = False
        TLS_CONTEXT.verify_mode = ssl.CERT_NONE


    def request(path, params=None, timeout=60):
        url = f"{API_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        key = KEY_FILE.read_text().strip()
        req = urllib.request.Request(
            url, headers={"Hydrus-Client-API-Access-Key": key}
        )
        return urllib.request.urlopen(
            req, timeout=timeout, context=TLS_CONTEXT
        )


    def available():
        try:
            if not KEY_FILE.read_text().strip():
                return False
            with request("/api_version", timeout=2):
                return True
        except Exception:
            return False


    def predicates(query):
        terms = [term.strip() for term in query.split(",") if term.strip()]
        return [RATING_PREDICATE, IMAGE_PREDICATE, *terms]


    def search(query, limit=None, return_hashes=True):
        terms = predicates(query)
        if limit is not None:
            terms.append(f"system:limit={limit}")
        with request(
            "/get_files/search_files",
            {
                "tags": json.dumps(terms),
                "file_sort_type": 4,
                "return_hashes": str(return_hashes).lower(),
            },
        ) as response:
            result = json.load(response)
            return result["hashes" if return_hashes else "file_ids"]


    def refresh(query, destination):
        destination = pathlib.Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = pathlib.Path(
            tempfile.mkdtemp(
                prefix="hydrus-wallpapers.", dir=destination.parent
            )
        )
        try:
            for file_hash in search(query, 16):
                with request(
                    "/get_files/file", {"hash": file_hash}
                ) as response:
                    content_type = response.headers.get_content_type()
                    extension = {
                        "image/jpeg": ".jpg",
                        "image/png": ".png",
                        "image/webp": ".webp",
                    }.get(content_type)
                    if extension is None:
                        continue
                    (temporary / f"{file_hash}{extension}").write_bytes(
                        response.read()
                    )
            shutil.rmtree(destination, ignore_errors=True)
            temporary.rename(destination)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise


    try:
        if len(sys.argv) == 2 and sys.argv[1] == "available":
            raise SystemExit(0 if available() else 1)
        if len(sys.argv) < 3:
            raise SystemExit(
                "usage: hydrus-wallpapers "
                "available|count QUERY|refresh QUERY DIR"
            )
        command, query = sys.argv[1:3]
        if command == "count":
            print(len(search(query, return_hashes=False)))
        elif command == "refresh" and len(sys.argv) == 4:
            refresh(query, sys.argv[3])
        else:
            raise SystemExit(
                "usage: hydrus-wallpapers "
                "available|count QUERY|refresh QUERY DIR"
            )
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read()).get("error", str(error))
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = str(error)
        raise SystemExit(f"Hydrus API: {message}")
    except urllib.error.URLError as error:
        raise SystemExit(f"Hydrus not reachable at {API_URL}: {error.reason}")
    except FileNotFoundError as error:
        raise SystemExit(
            f"Key file not found: {error.filename}\n"
            f"Save your Hydrus API key to {KEY_FILE}"
        )
  '';

  wallpaper = pkgs.writeShellApplication {
    name = "hypr-wallpaper";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.findutils
      pkgs.hyprland
      pkgs.imagemagick
      pkgs.jq
      pkgs.procps
    ];
    text = ''
      set -euo pipefail

      state_dir="''${XDG_STATE_HOME:-$HOME/.local/state}/hypr-wallpaper"
      mode_file="$state_dir/mode"
      source_file="$state_dir/source"
      theme_file="$state_dir/theme"
      weight_file="$state_dir/weights.tsv"
      hydrus_query_file="$state_dir/hydrus-query"
      hydrus_cache="''${XDG_CACHE_HOME:-$HOME/.cache}/hypr-wallpaper/hydrus"
      mkdir -p "$state_dir"
      [ -e "$weight_file" ] || : > "$weight_file"

      read_mode() {
        if [ -r "$mode_file" ]; then
          cat "$mode_file"
        else
          printf 'sfw\n'
        fi
      }

      read_theme() {
        if [ -r "$theme_file" ]; then
          cat "$theme_file"
        else
          printf 'yuri\n'
        fi
      }

      set_mode() {
        printf '%s\n' "$1" > "$mode_file"
      }

      read_source() {
        if [ -r "$source_file" ]; then
          cat "$source_file"
        else
          printf 'local\n'
        fi
      }

      hydrus_available() {
        ${lib.getExe hydrusWallpapers} available >/dev/null 2>&1
      }

      rotate() {
        mode="$(read_mode)"
        theme="$(read_theme)"
        source="$(read_source)"
        if [ "$mode" = "nsfw" ] && [ "$source" = "hydrus" ] && [ -r "$hydrus_query_file" ]; then
          query="$(cat "$hydrus_query_file")"
          if ! find "$hydrus_cache" -maxdepth 1 -type f -print -quit 2>/dev/null | grep -q .; then
            ${lib.getExe hydrusWallpapers} refresh "$query" "$hydrus_cache" || return 0
          fi
          directory="$hydrus_cache"
        else
          directory="${wallpaperRoot}/$theme/$mode"
        fi
        [ -d "$directory" ] || return 0

        category_dirs=()
        for category in general anime people; do
          if find "$directory/$category" -maxdepth 1 -type f -print -quit 2>/dev/null | grep -q .; then
            category_dirs+=("$directory/$category")
          fi
        done
        if [ "''${#category_dirs[@]}" -gt 0 ]; then
          category_index=$((RANDOM % ''${#category_dirs[@]}))
          directory="''${category_dirs[$category_index]}"
        fi

        for _ in $(seq 1 20); do
          ${awww} query >/dev/null 2>&1 && break
          sleep 0.2
        done
        ${awww} query >/dev/null 2>&1 || return 0

        monitor_data="$(hyprctl -j monitors)"
        wallpaper_query="$(${awww} query)"
        selected_images=()

        current_image_for() {
          printf '%s\n' "$wallpaper_query" \
            | awk -v output="$1" '
                index($0, ": " output ": ") && index($0, "currently displaying: image: ") {
                  sub(/^.*currently displaying: image: /, "")
                  print
                  exit
                }
              '
        }

        image_was_selected() {
          local selected
          for selected in "''${selected_images[@]}"; do
            [ "$selected" != "$1" ] || return 0
          done
          return 1
        }

        filter_candidates() {
          local candidates="$1"
          local previous_image="$2"
          local avoid_selected="$3"
          local avoid_previous="$4"

          while IFS=$'\t' read -r score image; do
            [ -n "$image" ] || continue
            if [ "$avoid_previous" = "yes" ] && [ -n "$previous_image" ] && [ "$image" = "$previous_image" ]; then
              continue
            fi
            if [ "$avoid_selected" = "yes" ] && image_was_selected "$image"; then
              continue
            fi
            printf '%s\t%s\n' "$score" "$image"
          done <<< "$candidates"
        }

        weighted_pick() {
          local images="$1"

          awk -v weights_file="$weight_file" -v seed="$RANDOM" '
            BEGIN {
              FS = "\t"
              srand(seed)
              while ((getline < weights_file) > 0) {
                if ($1 != "" && $2 > 0) {
                  weights[$1] = $2
                }
              }
            }
            {
              image = $0
              if (image == "") {
                next
              }
              weight = (image in weights) ? weights[image] : 1
              total += weight
              images[++count] = image
              totals[count] = total
            }
            END {
              if (count == 0) {
                exit 1
              }
              pick = rand() * total
              for (i = 1; i <= count; i++) {
                if (pick < totals[i]) {
                  print images[i]
                  exit
                }
              }
              print images[count]
            }
          ' <<< "$images"
        }

        update_weights() {
          local images="$1"
          local picked="$2"
          local tmp="$weight_file.tmp.$$"

          awk -v images="$images" -v picked="$picked" '
            BEGIN {
              FS = "\t"
              OFS = "\t"
              split(images, lines, "\n")
              for (i in lines) {
                if (lines[i] != "") {
                  eligible[lines[i]] = 1
                }
              }
            }
            {
              image = $1
              weight = $2 + 0
              if (image == "") {
                next
              }
              if (image in eligible) {
                weight = (image == picked) ? 1 : weight + 1
                seen[image] = 1
              }
              print image, weight
            }
            END {
              for (image in eligible) {
                if (!(image in seen)) {
                  print image, (image == picked) ? 1 : 2
                }
              }
            }
          ' "$weight_file" > "$tmp"
          mv "$tmp" "$weight_file"
        }

        pick_image() {
          local candidates="$1"
          local previous_image="$2"
          local filtered
          local best_score
          local pull_pool
          local image

          for constraints in both selected previous any; do
            case "$constraints" in
              both) filtered="$(filter_candidates "$candidates" "$previous_image" yes yes)" ;;
              selected) filtered="$(filter_candidates "$candidates" "$previous_image" yes no)" ;;
              previous) filtered="$(filter_candidates "$candidates" "$previous_image" no yes)" ;;
              any) filtered="$candidates" ;;
            esac

            [ -n "$filtered" ] || continue
            best_score="$(printf '%s\n' "$filtered" | cut -f1 | sort -n | head -n1)"
            pull_pool="$(
              printf '%s\n' "$filtered" \
                | awk -F '\t' -v score="$best_score" '$1 == score { sub(/^[^\t]*\t/, ""); print }'
            )"
            image="$(weighted_pick "$pull_pool")"
            update_weights "$pull_pool" "$image"
            printf '%s\n' "$image"
            return 0
          done

          return 1
        }

        while IFS=$'\t' read -r output width height; do
          candidates="$(
            find "$directory" -type f \
              \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) \
              -print0 \
              | while IFS= read -r -d "" image; do
                  dimensions="$(identify -ping -format '%w %h' "$image" 2>/dev/null || true)"
                  [ -n "$dimensions" ] || continue
                  read -r image_width image_height <<< "$dimensions"

                  if [ "$image_width" -eq "$width" ] && [ "$image_height" -eq "$height" ]; then
                    score=0
                  elif [ "$((image_width * height))" -eq "$((image_height * width))" ]; then
                    score=1
                  else
                    score=2
                  fi
                  printf '%s\t%s\n' "$score" "$image"
                done
          )"
          [ -n "$candidates" ] || continue
          previous_image="$(current_image_for "$output")"
          image="$(pick_image "$candidates" "$previous_image")"
          [ -n "$image" ] || continue
          selected_images+=("$image")
          "${awww}" img --outputs "$output" "$image" \
            --resize crop \
            --crop-gravity center \
            --transition-type any \
            --transition-duration 1.2 \
            --transition-step 90
        done < <(
          printf '%s' "$monitor_data" \
            | jq -r '.[] | [.name, (.width | tostring), (.height | tostring)] | @tsv'
        )
      }

      prepare_lockscreen() {
        theme="$(read_theme)"
        directory="${wallpaperRoot}/$theme/sfw"
        [ -d "$directory" ] || return 0

        image="$(
          find "$directory" -type f \
            \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) \
            | shuf -n1
        )"
        [ -n "$image" ] || return 0

        cache_dir="''${XDG_CACHE_HOME:-$HOME/.cache}/hypr-wallpaper"
        mkdir -p "$cache_dir"
        magick "$image" \
          -auto-orient \
          -resize '3840x2160^' \
          -gravity center \
          -extent 3840x2160 \
          "$cache_dir/lockscreen.next.png"
        mv "$cache_dir/lockscreen.next.png" "$cache_dir/lockscreen.png"
      }

      choose_theme() {
        choice="$(printf '%s\n' Yuri Trans Neutral | ${rofi} -dmenu -i -p "Wallpaper theme")"
        case "$choice" in
          Yuri) theme=yuri ;;
          Trans) theme=trans ;;
          Neutral) theme=neutral ;;
          *) return 0 ;;
        esac
        printf '%s\n' "$theme" > "$theme_file"
        printf 'local\n' > "$source_file"
        if [ ! -d "${wallpaperRoot}/$theme/$(read_mode)" ]; then
          set_mode sfw
        fi
        rotate
      }

      menu() {
        mode="$(read_mode)"
        theme="$(read_theme)"
        mode_label=""
        if [ -d "${wallpaperRoot}/$theme/nsfw" ]; then
          if [ "$mode" = "nsfw" ]; then
            mode_label="Disable NSFW mode"
          else
            mode_label="Enable NSFW mode"
          fi
        fi

        choice="$(
          {
            printf '%s\n' "Theme"
            [ -z "$mode_label" ] || printf '%s\n' "$mode_label"
            [ "$mode" != "nsfw" ] || ! hydrus_available || printf '%s\n' "Hydrus search"
            printf '%s\n' \
              "Rotate now" \
              "Choose an image" \
              "Restore previous" \
              "Clear wallpaper"
          } \
          | ${rofi} -dmenu -i -p "Wallpaper"
        )"

        case "$choice" in
          Theme)
            choose_theme
            ;;
          "Enable NSFW mode")
            set_mode nsfw
            rotate
            ;;
          "Disable NSFW mode")
            set_mode sfw
            printf 'local\n' > "$source_file"
            rotate
            ;;
          "Hydrus search")
            previous_query="$([ -r "$hydrus_query_file" ] && cat "$hydrus_query_file" || true)"
            query="$(
              printf '\n' \
                | ${rofi} -dmenu -filter "$previous_query" -p "Hydrus tags (comma-separated AND search)"
            )" || return 0
            if ! count="$(${lib.getExe hydrusWallpapers} count "$query" 2>&1)"; then
              printf '%s\n' "$count" | ${rofi} -dmenu -p "Hydrus error" >/dev/null
              return 0
            fi
            if [ "$count" -eq 0 ]; then
              printf 'No liked wallpapers match that search.\n' | ${rofi} -dmenu -p "Hydrus" >/dev/null
              return 0
            fi
            confirmation="$(
              printf '%s\n' "Use $count matching images" Cancel \
                | ${rofi} -dmenu -p "Replace wallpaper rotation?"
            )"
            [ "$confirmation" = "Use $count matching images" ] || return 0
            if ! refresh_error="$(${lib.getExe hydrusWallpapers} refresh "$query" "$hydrus_cache" 2>&1)"; then
              printf '%s\n' "$refresh_error" | ${rofi} -dmenu -p "Hydrus error" >/dev/null
              return 0
            fi
            printf '%s\n' "$query" > "$hydrus_query_file"
            printf 'hydrus\n' > "$source_file"
            rotate
            ;;
          "Rotate now")
            rotate
            ;;
          "Choose an image")
            exec hypr-rofi-wallpaper
            ;;
          "Restore previous")
            ${awww} restore
            ;;
          "Clear wallpaper")
            ${awww} clear 1e1e2eff
            ;;
        esac
      }

      case "''${1:-rotate}" in
        rotate)
          rotate
          ;;
        menu)
          menu
          ;;
        session-start)
          set_mode sfw
          printf 'local\n' > "$source_file"
          rotate
          prepare_lockscreen
          ;;
        lock)
          set_mode sfw
          rotate || true
          prepare_lockscreen
          pidof hyprlock >/dev/null || exec hyprlock
          ;;
        *)
          printf 'usage: hypr-wallpaper [rotate|menu|session-start|lock]\n' >&2
          exit 2
          ;;
      esac
    '';
  };
in
{
  home.packages = [ wallpaper ];

  wayland.windowManager.hyprland.settings."$wallpaperMenu" =
    lib.mkForce "${lib.getExe wallpaper} menu";

  programs.hyprlock.settings.background = lib.mkForce [
    {
      path = "${config.xdg.cacheHome}/hypr-wallpaper/lockscreen.png";
      color = "rgb(1e1e2e)";
      blur_passes = 2;
      blur_size = 4;
    }
  ];

  systemd.user.services.wallpaper-rotation = {
    Unit = {
      Description = "Choose resolution-matched wallpapers for each display";
      After = [
        "awww.service"
        config.wayland.systemd.target
      ];
      PartOf = [ config.wayland.systemd.target ];
      ConditionEnvironment = "WAYLAND_DISPLAY";
    };
    Service = {
      Type = "oneshot";
      ExecStart = "${lib.getExe wallpaper} rotate";
    };
  };

  systemd.user.timers.wallpaper-rotation = {
    Unit = {
      Description = "Rotate display wallpapers every 20 minutes";
      After = [ config.wayland.systemd.target ];
      PartOf = [ config.wayland.systemd.target ];
    };
    Timer = {
      OnActiveSec = "20min";
      OnUnitActiveSec = "20min";
      Unit = "wallpaper-rotation.service";
    };
    Install.WantedBy = [ config.wayland.systemd.target ];
  };
}
