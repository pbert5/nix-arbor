# Storage Fabric Inventory and Capabilities

This page is the config-facing guide for shaping the storage fabric in inventory.
Use it when you need to answer questions like “which file owns this default?” or
“what does this host need to declare to become an archive node?”.

## Where the config lives

| Concern | Path |
|---|---|
| site-wide storage-fabric defaults | `inventory/storage-fabric.nix` |
| per-host capability flags and overrides | `inventory/hosts.nix` |
| validation rules | `lib/validation/storage-fabric.nix` |

## Site-wide defaults

The top-level fabric defaults live under `storageFabric`.

### Transport defaults

```nix
storageFabric.transport = {
  privateNetwork = "privateYggdrasil";
  allowPublicContentTransfers = false;
};
```

This is the hard policy center of gravity: content transfers are private unless
someone changes the site policy deliberately.

### Annex defaults

```nix
storageFabric.annex = {
  repoRoot = "/srv/annex/cluster-data";
  user = "annex";
  group = "annex";
  defaultNumCopies = 2;
  metadataRemotes = [ "radicle" "github" ];
};
```

### SeaweedFS hot-pool defaults

```nix
storageFabric.seaweedfs.hotPool = {
  enable = true;
  replication = "001";
  masterPort = 9333;
  filerPort = 8888;
  s3Port = 8333;
  volumePort = 8090;
  mountPoint = "/hot";
  filerPath = "/srv/seaweedfs/filer";
  volumePath = "/srv/seaweedfs/volumes";
  s3.enable = false;
};
```

### Archive defaults

```nix
storageFabric.archive = {
  remotes = {
    tape.enable = false;
    nas.enable = false;
    object.enable = false;
    removableDisk.enable = false;
  };
  minArchiveCopies = 2;
};
```

## Storage-fabric capabilities

Storage-fabric responsibilities are declared directly under `org.*` in
`inventory/hosts.nix`. The matching dendrites are selected explicitly by the
host.

| Capability flag | Meaning | Required dendrite |
|---|---|---|
| `org.storage.annex.fabric.client` | regular content reader or writer | `storage/git-annex` |
| `org.storage.annex.fabric.storage` | stable annex transfer/storage node | `storage/git-annex` |
| `org.storage.annex.fabric.workstation` | user workstation copy policy | `storage/git-annex` |
| `org.storage.annex.fabric.computeCache` | ephemeral compute cache | `storage/git-annex` |
| `org.storage.seaweedfs.master` | SeaweedFS coordinator | `storage/seaweedfs-hot` |
| `org.storage.seaweedfs.volume` | SeaweedFS volume host | `storage/seaweedfs-hot` |
| `org.storage.seaweedfs.filer` | SeaweedFS filer and `/hot` surface | `storage/seaweedfs-hot` |
| `org.storage.seaweedfs.s3` | SeaweedFS S3 gateway | `storage/seaweedfs-hot` |
| `org.storage.annex.fabric.archive` | durable archive host | `storage/archive` |
| `org.network.radicle.seed` | private metadata seed | `network/radicle` |
| `org.storage.observability.enable` | health tooling and timers | `storage/storage-observability` |

## Per-host overrides

Host-specific fabric details live under `org.*` in `inventory/hosts.nix`.

### Common host override shapes

```nix
org.storage.annex = {
  group = "archive";
  fabric = {
    storage = true;
    archive = true;
  };
  archive.nas = {
    enable = true;
    path = "/srv/annex/archive/nas";
  };
};

org.network.radicle = {
  seed = true;
  # Optional: only set this for a custom $RAD_HOME/keys/radicle path.
  privateKeyFile = "/run/radicle/keys/radicle";
  repos = [ "flake-devbox" "cluster-data" ];
};
```

Tape-backed archive hosts also need tape manager settings, which are separate
from the generic storage-fabric defaults:

```nix
org.storage.tape = {
  manager = "fossilsafe";
  fossilsafe.stateDir = "/var/lib/fossilsafe";
};
```

## Current declared hosts

### `r640-0`

`r640-0` currently enables:

- `annex-storage`
- `seaweed-master`
- `seaweed-volume`
- `seaweed-filer`
- `archive-node`
- `radicle-seed`
- `storage-fabric-observer`

Host-specific fabric overrides on `r640-0` include:

- annex preferred-content group `archive`
- NAS archive path `/mypool/annex-archive/nas`
- Radicle private key path and repo list

### `desktoptoodle`

`desktoptoodle` currently enables:

- `annex-storage`
- `seaweed-volume`
- `seaweed-filer`
- `radicle-seed`
- `storage-fabric-observer`

Host-specific fabric overrides on `desktoptoodle` include:

- annex preferred-content group `archive`
- Radicle private key path and repo list

## Enrollment checklist for a new storage host

1. add the host to `inventory/hosts.nix`
2. leave `org.network.membership.optIn = "all"` or explicitly include
   `privateYggdrasil`
3. enable the storage-fabric `org.*` capability flags it will carry
4. add the matching dendrites
5. set `org.storage.annex.group`
6. enable at least one archive backend if using `archive-node`
7. add backend-specific facts, such as tape devices or archive paths
8. let `network/radicle` use its metadata-declared identity target path, or set
   `org.network.radicle.privateKeyFile` only when using a custom key
9. set `org.network.radicle.seed` when the host should advertise as a seed
10. run `nix flake check`

## Example host snippets

### NAS archive node

```nix
my-storage-node = {
  dendrites = [
    "storage/git-annex"
    "storage/archive"
    "storage/storage-observability"
  ];
  org.network.membership.optIn = "all";
  org.storage.annex = {
    group = "archive";
    fabric = {
      storage = true;
      archive = true;
    };
    archive.nas = {
      enable = true;
      path = "/srv/annex/archive/nas";
    };
  };
  org.storage.observability.enable = true;
};
```

### Tape archive node

```nix
my-tape-node = {
  dendrites = [
    "storage/git-annex"
    "storage/archive"
    "storage/storage-observability"
    "storage/tape"
  ];
  org.network.membership.optIn = "all";
  facts.storage.tape.devices = {
    changer = "/dev/tape/by-id/REPLACE_ME";
    drives = [ "/dev/tape/by-id/REPLACE_ME" ];
  };
  org.storage.annex.fabric = {
    storage = true;
    archive = true;
  };
  org.storage.annex.archive.tape.enable = true;
  org.storage.observability.enable = true;
  org.storage.tape.manager = "fossilsafe";
  fruits = [ "fossilsafe" ];
};
```

## Validation expectations

The validation layer checks that inventory promises are coherent. Examples:

- storage hosts must be on the private overlay
- SeaweedFS topology must match the declared replication level
- archive nodes must enable a real backend
- tape and object archives must provide the required facts or endpoints
- content remotes must not point at public Git or public-looking endpoints

For the detailed list, see [`../policy/validation.md`](../policy/validation.md).
