# Storage Fabric Command Reference

This page is the quick lookup table for the commands that show up most often in
storage-fabric work.

## `cluster-annex`

The `cluster-annex` helper comes from
`dendrites/storage/dendrites/git-annex/leaves/helpers.nix`.

| Command | What it does | Notes |
|---|---|---|
| `cluster-annex init` | initialize the annex repo on this host | creates the repo if missing and sets `numcopies` |
| `cluster-annex set-group <group>` | set the local preferred-content group | usually `archive`, `workstation`, `compute`, or `hot` |
| `cluster-annex add-remote <name> <host-alias>` | add a peer annex remote over Ygg | builds `annex+ssh://<host-alias>/srv/annex/cluster-data` |
| `cluster-annex get-active <project>` | fetch active project files | pulls `projects/<project>/` through annex |
| `cluster-annex sync [remote]` | sync metadata with peers | passes through to `git annex sync --jobs=4` |
| `cluster-annex sync-all` | sync metadata and content | uses `git annex sync --content` |
| `cluster-annex whereis [path]` | show copy locations | useful before drops or recovery |
| `cluster-annex drop-safe <path>` | drop data only if policy allows | uses annex auto-drop safety |
| `cluster-annex archive <path>` | copy content to archive remotes | targets the `archive` remote group |
| `cluster-annex fsck-important` | fsck `*.important` files | focused health check |
| `cluster-annex stage <project>` | copy an active project into `/hot` | populates `/hot/projects/<project>` |
| `cluster-annex unstage <project>` | remove the staged project from `/hot` | cache cleanup only |
| `cluster-annex job-stage <project> <job-id>` | prepare a job workspace under `/hot/scratch/<job-id>` | creates `input/` and `output/` |
| `cluster-annex job-publish <job-id>` | publish job outputs into annex and sync them | copies from `/hot/scratch/<job-id>/output` |
| `cluster-annex job-clean <job-id>` | remove hot staging for a finished job | also attempts a safe drop of outputs from hot staging |
| `cluster-annex status` | show annex and hot-pool health | helper-local status output |

## `fabric-status`

`fabric-status` comes from the observability dendrite and is the fastest single
command for a high-level check.

```bash
fabric-status
```

It checks, where relevant on the current host:

- whether the annex repo exists
- whether files are lacking the configured minimum copy count
- whether remotes and annex SSH keys exist
- whether SeaweedFS services are active
- whether `/hot` is mounted
- whether `radicle-seed` is active

## Observability units

| Command | Use it for |
|---|---|
| `systemctl status annex-fsck-daily.service --no-pager` | inspect the last daily annex copy-safety run |
| `systemctl start annex-fsck-daily.service` | run the annex copy-safety check immediately |
| `systemctl status annex-fsck-daily.timer --no-pager` | verify the daily timer schedule |

## Core git-annex commands

Sometimes the helper is not enough, and raw annex commands are clearer.

| Command | Use it for |
|---|---|
| `git -C /srv/annex/cluster-data annex add <path>` | add new content |
| `git -C /srv/annex/cluster-data annex sync` | sync metadata |
| `git -C /srv/annex/cluster-data annex whereis <path>` | inspect copy locations |
| `git -C /srv/annex/cluster-data annex get <path> --auto` | restore content from available remotes |
| `git -C /srv/annex/cluster-data annex get <path> --from=<remote>` | restore from a chosen backend |
| `git -C /srv/annex/cluster-data annex drop <path>` | remove a local copy when policy permits |
| `git -C /srv/annex/cluster-data annex fsck <path>` | verify content health |
| `git -C /srv/annex/cluster-data annex remotes` | inspect configured annex remotes |
| `git -C /srv/annex/cluster-data remote -v` | inspect Git remotes |

## P2P git-annex commands

The `storage/git-annex` dendrite installs Tor, Magic Wormhole, and the
`git-annex-p2p-iroh` helper. It also runs `annex-remotedaemon` for hosts that
initialize the cluster annex repo.

Run P2P setup commands inside the annex repo as the repo owner:

| Command | Use it for |
|---|---|
| `git annex p2p --enable tor` | enable git-annex's built-in Tor P2P transport |
| `git annex p2p --enable iroh` | enable Iroh P2P transport through `git-annex-p2p-iroh` |
| `git annex p2p --pair` | exchange pairing codes with another repo |
| `git annex p2p --gen-addresses` | generate a manual pairing address |
| `git annex p2p --link --name <name>` | link a peer from a manual pairing address |
| `systemctl status annex-remotedaemon --no-pager` | inspect the long-running P2P listener |

On NixOS, Tor normally runs with a generated config in the Nix store. The
dendrite creates a writable `/etc/tor/torrc` include so `git annex p2p --enable
tor` can add its hidden-service stanza while the active Tor service still
remains NixOS-managed. The installed `git-annex` wrapper also routes Tor setup
through `sudo`, because upstream git-annex otherwise tries `su` or graphical
polkit helpers first on some interactive shells. Hosts still need a narrow
sudoers rule for the repo owner; `t320-0` allows `user1` to run only
`git-annex enable-tor 1000` without a password. The wrapper preserves a narrow
PATH containing `systemctl`, which root-side `git-annex enable-tor` needs when
it reloads Tor after writing the hidden-service stanza.

Iroh addresses are generated by the `git-annex-p2p-iroh` helper through
`dumbpipe`. A repository can print an Iroh address before its listener is
actually running; if linking fails with `No addressing information available`,
run `git annex p2p --enable iroh` and restart `git annex remotedaemon` for the
repository so `dumbpipe listen-unix` starts for that endpoint.

## SeaweedFS commands

| Command | Use it for |
|---|---|
| `systemctl status seaweedfs-master --no-pager` | master health |
| `systemctl status seaweedfs-volume --no-pager` | volume health |
| `systemctl status seaweedfs-filer --no-pager` | filer health |
| `systemctl status seaweedfs-hot-mount --no-pager` | `/hot` mount health |
| `weed shell -master=<ygg-addr>:9333 <<< "volume.list"` | volume map and registration |
| `mountpoint /hot` | quick mount check |
| `df -h /hot` | hot-pool capacity |

## Radicle commands

| Command | Use it for |
|---|---|
| `systemctl status radicle-seed --no-pager` | seed service health |
| `rad node status` | node health |
| `rad node routing` | peer routing |
| `rad sync --fetch <repo-id>` | force metadata sync |

## Validation and evaluation

| Command | Use it for |
|---|---|
| `nix flake check` | run storage-fabric validation and other repo checks |
| `nix eval .#inventory.storageFabric --json | jq .` | inspect effective site defaults |
| `systemctl show seaweedfs-volume -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges` | verify sandboxing |
| `ss -tlnp | grep -E '(:9333|:19333|:8090|:18090|:8888|:18888|:8333)'` | confirm private-only listening surfaces |

## When to leave this page

- for procedures, go to [`runbook.md`](../runbook.md)
- for recovery exercises, go to [`restore-drills.md`](../restore-drills.md)
- for failure diagnosis, go to [`troubleshooting.md`](../troubleshooting.md)
