{
  lib,
  pkgs,
  site ? { },
  ...
}:
let
  endpoints = import ../../../../lib/endpoints.nix { inherit lib; };
  hydruiEndpoint = endpoints.normalizeEndpoint 45870 (site.ports.hydrui or { });
  hydruiUrl = "http://127.0.0.1:${toString hydruiEndpoint.port}";
  pinnedPkgs =
    commit: sha256:
    import
      (builtins.fetchTarball {
        url = "https://github.com/NixOS/nixpkgs/archive/${commit}.tar.gz";
        inherit sha256;
      })
      {
        system = pkgs.stdenv.hostPlatform.system;
        config = { };
      };

  hydrusPackages = {
    "652" =
      (pinnedPkgs "0744ef1b047f07d31d9962d757ffe38ec14a4d41" "sha256-SosfgQSqVmOkqVgNYJnxW5FvoIQX4grOcpIKNrIwz4o=")
      .hydrus;
    "${pkgs.hydrus.version}" = pkgs.hydrus;
  };

  hydrusPackageLines = lib.concatStringsSep "\n" (
    lib.mapAttrsToList (version: package: ''
      HYDRUS_EXES["${version}"]="${lib.getExe' package "hydrus-client"}"
    '') hydrusPackages
  );

  hydrusWatcherTagger = pkgs.writers.writePython3Bin "hydrus-watcher-tagger" { } ''
    import html
    import json
    import os
    import ssl
    import sys
    import unicodedata
    import urllib.error
    import urllib.parse
    import urllib.request

    API_URL = os.environ.get("HYDRUS_API_URL", "https://127.0.0.1:45869")
    TLS_VERIFY = os.environ.get("HYDRUS_TLS_VERIFY", "0") == "1"
    TAG_SERVICE = os.environ.get("HYDRUS_TAG_SERVICE", "my tags")
    TAG_NAMESPACE = os.environ.get("HYDRUS_TAG_NAMESPACE", "thread")
    LEGACY_TAG_NAMESPACE = os.environ.get(
        "HYDRUS_LEGACY_TAG_NAMESPACE", "watcher"
    )
    DRY_RUN = os.environ.get("HYDRUS_DRY_RUN", "0") == "1"
    _config_home = os.environ.get(
        "XDG_CONFIG_HOME", os.path.expanduser("~/.config")
    )
    KEY_FILE = os.environ.get(
        "HYDRUS_KEY_FILE",
        os.path.join(_config_home, "hydrus-watcher-tagger", "access_key"),
    )

    # All statuses where the file is actually in the local database:
    # 1=new  2=redundant (already in db)  9=child files created
    IMPORT_STATUS_IN_DB = {1, 2, 9}
    TLS_CONTEXT = None
    if API_URL.startswith("https://"):
        TLS_CONTEXT = ssl.create_default_context()
        if not TLS_VERIFY:
            TLS_CONTEXT.check_hostname = False
            TLS_CONTEXT.verify_mode = ssl.CERT_NONE


    def get_access_key():
        key = os.environ.get("HYDRUS_ACCESS_KEY")
        if key:
            return key.strip()
        try:
            with open(KEY_FILE) as f:
                return f.read().strip()
        except FileNotFoundError:
            print(
                f"No API key found. Write your Hydrus Client API key to:\n"
                f"  {KEY_FILE}\n"
                "Enable: Services → Manage Services → Client API.",
                file=sys.stderr,
            )
            return None


    ACCESS_KEY = get_access_key()
    HEADERS = {"Hydrus-Client-API-Access-Key": ACCESS_KEY}


    def api_get(path, params=None):
        url = f"{API_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(
                req, timeout=30, context=TLS_CONTEXT
            ) as resp:
                return json.loads(resp.read())
        except urllib.error.URLError as e:
            print(f"Hydrus API unavailable ({API_URL}): {e}", file=sys.stderr)
            sys.exit(0)  # not an error — Hydrus just isn't running


    def api_post(path, body):
        url = f"{API_URL}{path}"
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={**HEADERS, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            req, timeout=30, context=TLS_CONTEXT
        ) as resp:
            return json.loads(resp.read()) if resp.length else {}


    def iter_leaf_pages(node):
        children = node.get("pages", [])
        if children:
            for child in children:
                yield from iter_leaf_pages(child)
        else:
            yield node


    def normalize_subject(subject):
        subject = unicodedata.normalize("NFKC", html.unescape(subject))
        subject = "".join(
            " " if unicodedata.category(char).startswith("C") else char
            for char in subject
        )
        return " ".join(subject.split())


    def main():
        if ACCESS_KEY is None:
            return

        version = api_get("/api_version")
        print(f"Hydrus API v{version['version']}")

        pages_resp = api_get("/manage_pages/get_pages")
        total_tagged = 0
        watcher_page_count = 0

        for page in iter_leaf_pages(pages_resp["pages"]):
            page_key = page["page_key"]
            info = api_get(
                "/manage_pages/get_page_info",
                {"page_key": page_key, "simple": "false"},
            )
            management = info["page_info"].get("management", {})
            watchers = management.get("multiple_watcher_import", {}).get(
                "watcher_imports", []
            )
            if not watchers:
                continue

            watcher_page_count += 1
            name = page.get("name", page_key)
            print(f"\nPage '{name}' — {len(watchers)} watcher(s)")

            for w in watchers:
                original_subject = (w.get("subject") or "").strip()
                subject = normalize_subject(original_subject)
                if not subject:
                    print(f"  [skip] no subject yet for {w.get('url', '?')[:70]}")
                    continue

                import_items = w.get("imports", {}).get("import_items", [])
                hashes = [
                    item["hash"]
                    for item in import_items
                    if item.get("hash")
                    and item.get("status") in IMPORT_STATUS_IN_DB
                ]

                if not hashes:
                    print(f"  [skip] no imported files for '{subject}'")
                    continue

                tag = f"{TAG_NAMESPACE}:{subject}" if TAG_NAMESPACE else subject
                print(f"  '{subject}' → {len(hashes)} file(s) → tag '{tag}'")

                if DRY_RUN:
                    continue

                for i in range(0, len(hashes), 256):
                    actions = {"0": [tag]}
                    if LEGACY_TAG_NAMESPACE:
                        actions["1"] = [
                            f"{LEGACY_TAG_NAMESPACE}:{original_subject}"
                        ]
                    api_post("/add_tags/add_tags", {
                        "hashes": hashes[i:i + 256],
                        "service_names_to_actions_to_tags": {
                            TAG_SERVICE: actions
                        },
                        "create_new_deleted_mappings": False,
                    })

                total_tagged += len(hashes)

        if watcher_page_count == 0:
            print("No thread watcher pages open.")
            return

        if DRY_RUN:
            print("\nDry run — set HYDRUS_DRY_RUN=0 to apply.")
        else:
            print(f"\nDone. Tagged {total_tagged} file(s) across all watchers.")


    if __name__ == "__main__":
        main()
  '';

  hydrusLauncher = pkgs.writeShellApplication {
    name = "hydrus-library-menu";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.findutils
      pkgs.gawk
      pkgs.gnused
      pkgs.python3
      pkgs.rofi
      pkgs.sqlite
      pkgs.wl-clipboard
      pkgs.xdg-utils
    ];
    text = ''
      current_version="${pkgs.hydrus.version}"
      declare -A HYDRUS_EXES
      ${hydrusPackageLines}

      KEY_DIR="''${XDG_CONFIG_HOME:-$HOME/.config}/hydrus-watcher-tagger"
      HYDRUI_URL_DEFAULT="${hydruiUrl}"
      HYDRUS_API_URL_DEFAULT="https://127.0.0.1:45869"

      key_file_for() {
        hash="$(printf '%s' "$1" | sha256sum | cut -c1-16)"
        printf '%s/keys/%s.key' "$KEY_DIR" "$hash"
      }

      name_file_for() {
        hash="$(printf '%s' "$1" | sha256sum | cut -c1-16)"
        printf '%s/keys/%s.name' "$KEY_DIR" "$hash"
      }

      activate_key_for() {
        kf="$(key_file_for "$1")"
        [ -f "$kf" ] || return 0
        mkdir -p "$KEY_DIR"
        cp "$kf" "$KEY_DIR/access_key"
        chmod 600 "$KEY_DIR/access_key"
      }

      manage_api_key() {
        label="$1"
        db_dir="$2"
        nf="$(name_file_for "$db_dir")"
        kf="$(key_file_for "$db_dir")"

        default_name="$([ -f "$nf" ] && cat "$nf" || printf '%s' "$label")"
        name="$(printf '%s' "$default_name" | rofi -dmenu -p "Key label")" || return 0
        [ -n "$name" ] || return 0

        api_key="$(rofi -dmenu -p "Paste API key" -password </dev/null)" || return 0
        [ -n "$api_key" ] || return 0

        mkdir -p "$(dirname "$kf")"
        printf '%s' "$api_key" > "$kf"
        printf '%s' "$name" > "$nf"
        chmod 600 "$kf"
        activate_key_for "$db_dir"

        show_text "API key saved" "Key '$name' saved and set as active.\n\n$db_dir"
      }

      urlencode() {
        python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
      }

      open_hydrui_for() {
        label="$1"
        db_dir="$2"
        kf="$(key_file_for "$db_dir")"

        if [ ! -r "$kf" ]; then
          show_text "HydrUI" "No Hydrus Client API key is saved for:\n\n$label\n\nChoose Set API key in this submenu first."
          return 0
        fi

        api_key="$(tr -d '\r\n' < "$kf")"
        if [ -z "$api_key" ]; then
          show_text "HydrUI" "The saved API key for this library is empty.\n\nChoose Replace API key in this submenu."
          return 0
        fi

        activate_key_for "$db_dir"

        hydrui_url="''${HYDRUI_URL:-$HYDRUI_URL_DEFAULT}"
        hydrus_api_url="''${HYDRUS_API_URL:-$HYDRUS_API_URL_DEFAULT}"
        exec xdg-open "$hydrui_url/#baseUrl=$(urlencode "$hydrus_api_url")&apiKey=$(urlencode "$api_key")"
      }

      db_version() {
        sqlite3 "$1/client.db" 'select version from version;' 2>/dev/null | head -n 1
      }

      version_available() {
        [ -n "''${HYDRUS_EXES[$1]:-}" ]
      }

      recommended_version() {
        db="$1"

        if [ "$db" -gt "$current_version" ]; then
          printf '%s\n' "$db"
        elif [ "$(( current_version - db ))" -le 50 ]; then
          printf '%s\n' "$current_version"
        else
          printf '%s\n' "$(( db + 45 ))"
        fi
      }

      nearest_stepping_version() {
        local db="$1"
        local target="$(( db + 10 ))"
        local best="" best_dist=999999 dist
        for version in "''${!HYDRUS_EXES[@]}"; do
          [ "$version" -gt "$db" ] || continue
          dist=$(( version - target ))
          [ "$dist" -lt 0 ] && dist=$(( -dist ))
          if [ "$dist" -lt "$best_dist" ]; then
            best_dist="$dist"
            best="$version"
          fi
        done
        printf '%s\n' "''${best:-$(( db + 10 ))}"
      }

      status_for() {
        db="$1"
        recommended="$(recommended_version "$db")"

        if version_available "$db"; then
          printf 'exact Hydrus v%s available' "$db"
        elif version_available "$recommended"; then
          printf 'can update with Hydrus v%s' "$recommended"
        elif [ "$db" -gt "$current_version" ]; then
          printf 'needs newer Hydrus v%s' "$db"
        else
          printf 'needs intermediate Hydrus v%s or earlier' "$recommended"
        fi
      }

      db_label() {
        db_dir="$1"
        parent="$(basename "$(dirname "$db_dir")")"
        name="$(basename "$db_dir")"

        if [ "$name" = "db" ]; then
          printf '%s/%s' "$parent" "$name"
        else
          printf '%s' "$name"
        fi
      }

      discover() {
        printf 'Base Hydrus profile | current v%s\t__base__\tnew\n' "$current_version"

        roots="''${HYDRUS_LIBRARY_ROOTS:-$HOME/.local/share/hydrus:$HOME/Hydrus:/mnt/bitlocker/hydrus}"
        IFS=':' read -r -a root_array <<< "$roots"

        existing_roots=()
        for root in "''${root_array[@]}"; do
          [ -d "$root" ] && existing_roots+=("$root")
        done

        [ "''${#existing_roots[@]}" -gt 0 ] || return 0

        find "''${existing_roots[@]}" -maxdepth 6 -type f -name client.db -print 2>/dev/null \
          | sort -u \
          | while read -r client_db; do
              db_dir="$(dirname "$client_db")"
              version="$(db_version "$db_dir")"
              [ -n "$version" ] || continue

              printf '%s | db v%s | %s\t%s\t%s\n' \
                "$(db_label "$db_dir")" \
                "$version" \
                "$(status_for "$version")" \
                "$db_dir" \
                "$version"
            done
      }

      show_text() {
        prompt="$1"
        text="$2"

        printf '%s\n' "$text" | rofi -dmenu -i -p "$prompt" >/dev/null
      }

      version_hint() {
        target="$1"

        case "$target" in
          580)
            printf 'Hydrus v580 is already pinned from nixpkgs 4284c2b73c8bce4b46a6adf23e16d9e2ec8da4bb.\n'
            ;;
          "$current_version")
            printf 'Hydrus v%s is the current flake package: pkgs.hydrus.\n' "$current_version"
            ;;
          *)
            cat <<EOF
      Hydrus v$target is not pinned in this flake yet.

      Find the nixpkgs commit for this version, then add it to hydrusPackages in:
        dendrites/desktop/dendrites/hydrus/hydrus-home.nix

      Useful lookup:
        NixHub package history for hydrus v$target

      After that, rebuild desktoptoodle and this launcher will offer it automatically.
      EOF
            ;;
        esac
      }

      copy_version_hint() {
        target="$1"
        hint="$(version_hint "$target")"
        printf '%s' "$hint" | wl-copy
        show_text "Hydrus v$target" "Copied version hint to the clipboard.\n\n$hint"
      }

      launch_version() {
        target="$1"
        db_dir="$2"

        if ! version_available "$target"; then
          show_text "Hydrus v$target" "$(version_hint "$target")"
          return 0
        fi

        if [ "$db_dir" = "__base__" ]; then
          exec "''${HYDRUS_EXES[$target]}"
        fi

        activate_key_for "$db_dir"
        exec "''${HYDRUS_EXES[$target]}" --db_dir "$db_dir"
      }

      set_specific_version() {
        db_dir="$1"
        default_version="$2"

        target="$(printf '%s\n' "$default_version" | rofi -dmenu -i -p "Hydrus version")"
        [ -n "$target" ] || return 0

        if ! [[ "$target" =~ ^[0-9]+$ ]]; then
          show_text "Hydrus version" "Please enter a numeric Hydrus version, like 580 or $current_version."
          return 0
        fi

        launch_version "$target" "$db_dir"
      }

      library_menu() {
        label="$1"
        db_dir="$2"
        db="$3"

        if [ "$db_dir" = "__base__" ]; then
          choice="$(printf '%s\n' \
            "Launch current Hydrus v$current_version" \
            "Set specific Hydrus version" \
            "Show details" \
            | rofi -dmenu -i -p "Hydrus"
          )"

          case "$choice" in
            "Launch current Hydrus v$current_version") launch_version "$current_version" "$db_dir" ;;
            "Set specific Hydrus version") set_specific_version "$db_dir" "$current_version" ;;
            "Show details") show_text "Hydrus" "Base Hydrus profile\nPackaged Hydrus: v$current_version\nNo external --db_dir will be passed." ;;
          esac

          return 0
        fi

        recommended="$(recommended_version "$db")"
        ten_target="$(nearest_stepping_version "$db")"
        one_target="$(( db + 1 ))"

        options=()

        if version_available "$db"; then
          options+=("Launch exact Hydrus v$db")
        fi

        if [ "$recommended" != "$db" ]; then
          options+=("Launch/update with recommended Hydrus v$recommended")
        fi

        key_label="$([ -f "$(key_file_for "$db_dir")" ] && printf 'Replace API key' || printf 'Set API key')"

        options+=(
          "Open in HydrUI"
          "Get recommended Hydrus v$recommended"
          "Set specific Hydrus version"
          "Upgrade by 10 to Hydrus v$ten_target"
          "Upgrade by 1 to Hydrus v$one_target"
          "Open database folder"
          "$key_label"
          "Show details"
        )

        choice="$(printf '%s\n' "''${options[@]}" | rofi -dmenu -i -p "Hydrus v$db")"

        case "$choice" in
          "Launch exact Hydrus v$db") launch_version "$db" "$db_dir" ;;
          "Launch/update with recommended Hydrus v$recommended") launch_version "$recommended" "$db_dir" ;;
          "Open in HydrUI") open_hydrui_for "$label" "$db_dir" ;;
          "Get recommended Hydrus v$recommended") copy_version_hint "$recommended" ;;
          "Set specific Hydrus version") set_specific_version "$db_dir" "$recommended" ;;
          "Upgrade by 10 to Hydrus v$ten_target") launch_version "$ten_target" "$db_dir" ;;
          "Upgrade by 1 to Hydrus v$one_target") launch_version "$one_target" "$db_dir" ;;
          "Open database folder") exec xdg-open "$db_dir" ;;
          "Set API key"|"Replace API key") manage_api_key "$label" "$db_dir" ;;
          "Show details")
            show_text "Hydrus v$db" "$label

      Database directory:
      $db_dir

      Database version: v$db
      Current packaged version: v$current_version
      Recommended next version: v$recommended
      Upgrade-by-10 target: v$ten_target
      Upgrade-by-1 target: v$one_target"
            ;;
        esac
      }

      if [ "''${1:-}" = "--list" ]; then
        discover
        exit 0
      fi

      if [ "''${1:-}" = "--key-setup" ]; then
        choice="$(discover | rofi -dmenu -i -p "Hydrus library")"
        [ -n "$choice" ] || exit 0
        label="$(printf '%s' "$choice" | cut -f1)"
        db_dir="$(printf '%s' "$choice" | cut -f2)"
        [ "$db_dir" = "__base__" ] && exit 0
        manage_api_key "$label" "$db_dir"
        exit 0
      fi

      choice="$(discover | rofi -dmenu -i -p "Hydrus libraries")"
      [ -n "$choice" ] || exit 0

      label="$(printf '%s' "$choice" | cut -f1)"
      db_dir="$(printf '%s' "$choice" | cut -f2)"
      version="$(printf '%s' "$choice" | cut -f3)"

      library_menu "$label" "$db_dir" "$version"
    '';
  };

  hydrusKeySetup = pkgs.writeShellApplication {
    name = "hydrus-key-setup";
    runtimeInputs = [ hydrusLauncher ];
    text = "exec hydrus-library-menu --key-setup";
  };
in
{
  desktop.hyprland.extraMenuEntries.Hydrus = "hydrus-library-menu";

  xdg.desktopEntries.hydrus-library-menu = {
    name = "Hydrus Libraries";
    genericName = "Image Library";
    exec = "hydrus-library-menu";
    icon = "image-x-generic";
    terminal = false;
    categories = [
      "Graphics"
      "FileTools"
      "Utility"
    ];
  };

  systemd.user.services.hydrus-watcher-tagger = {
    Unit.Description = "Tag Hydrus watcher files with watcher subject";
    Service = {
      Type = "oneshot";
      ExecStart = "${hydrusWatcherTagger}/bin/hydrus-watcher-tagger";
    };
  };

  systemd.user.timers.hydrus-watcher-tagger = {
    Unit.Description = "Periodic Hydrus watcher auto-tagging";
    Timer = {
      OnCalendar = "*:0/10";
      Persistent = true;
    };
    Install.WantedBy = [ "timers.target" ];
  };

  home.packages = [
    hydrusKeySetup
    hydrusLauncher
    hydrusWatcherTagger
  ];
}
