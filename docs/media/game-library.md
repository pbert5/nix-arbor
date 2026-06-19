# Game Library

The shared game library is stored on `t320-0` at `/big/GameLibrary` and mounted
on client hosts at `/srv/games`.

## Current Layout

- `t320-0` enables `media/game-library/export` and serves `/big/GameLibrary`
  over NFS.
- `t320-0` also runs the `romm` fruit. RomM stores its application state,
  configuration, database data, assets, resources, and local env files under
  `/var/lib/romm` on the root filesystem.
- RomM uses the fast local library at `/fast/GameLibrary` and publishes its web
  UI on port `8095`.
- RomM scan parallelism is set with `SCAN_WORKERS=10`, half of the 20 online CPU
  threads on `t320-0`.
- `r640-0` and `desktoptoodle` enable `media/game-library` and mount that
  export at `/srv/games`.
- home-directory symlinks such as `/home/example/games` continue to point at
  `/srv/games`.
- `desktoptoodle` also has a local Steam library on the BitLocker-mounted
  `/mnt/bitlocker/piss_boi/games` volume. Game payloads can live there, but
  Proton compatdata is bind-mounted from the native Linux filesystem at
  `/home/example/.local/share/Steam/steamapps/compatdata-piss-boi` onto
  `/mnt/bitlocker/piss_boi/games/steamapps/compatdata`. Proton prefixes need
  Windows-drive symlink names such as `c:`, which the NTFS `windows_names`
  mount option rejects.
- On `t320-0`, `/big/GameLibrary` and `/fast/GameLibrary` are owned by
  `user1:home-share` with the setgid bit on shared metadata directories so new
  files stay accessible to both local users. The fast mirror's mutable content
  roots and `.git` metadata are also recursively normalized to
  `user1:home-share` by tmpfiles, because root-owned worktree directories prevent
  `user1` from completing normal `git annex sync` checkouts. The fast local
  library ownership is important for git-annex P2P setup: git-annex uses the
  worktree root as an ownership template when writing
  `.git/annex/creds/p2paddrs.new`, so a root-owned `/fast/GameLibrary` makes
  non-root P2P enablement fail. Local users also get declarative Git
  `safe.directory` entries for `/big/GameLibrary` and `/fast/GameLibrary`.
- `game-library-annex-remotedaemon.service` starts the `user1` git-annex P2P
  listener for `/big/GameLibrary` on `t320-0`. It enables Iroh before starting
  the daemon and keeps `/run/current-system/sw/bin` in the service path so the
  `git-annex-p2p-iroh` helper is discoverable. Before starting, it clears stale
  repo-local `git-annex` and `dumbpipe` listener processes so old manual daemon
  starts do not leave duplicate Iroh endpoints behind. Tor and Iroh P2P pairing
  can exchange codes or addresses without the listener, but peers cannot connect
  back to `t320-0` unless the listener is running for the enabled transport.

## Inventory Surface

`inventory/storage/storage.nix` defines:

- the client mount source and mount options
- the backing dataset path on the source host
- the allowed NFS client hosts and export options

Update that inventory entry if the source host, export path, or allowed clients
change.

## RomM

The `romm` fruit is attached to `t320-0` from `inventory/hosts.nix`.

Runtime secrets such as database passwords and `ROMM_AUTH_SECRET_KEY` are
generated locally by `romm-secrets.service` and stored in
`/var/lib/romm/secrets/runtime.env`. Metadata-provider API keys live in the
root-only `/var/lib/romm/secrets/providers.env` file on `t320-0`; do not put
those keys in tracked Nix files.
