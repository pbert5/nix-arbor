# Registry Operations

## Command Surface

Registry commands:

```bash
clusterctl registry init
clusterctl registry validate
clusterctl registry reconcile
clusterctl registry materialize
clusterctl registry sync
clusterctl registry push
clusterctl registry notify
clusterctl registry status
```

Identity commands:

```bash
clusterctl identity publish
clusterctl identity publish --node HOST
clusterctl identity publish --service SERVICE
clusterctl identity publish-public NODE SERVICE --generation N
clusterctl identity promote NODE SERVICE --generation N
clusterctl identity burn NODE SERVICE --generation N --fingerprint FINGERPRINT --reason REASON
clusterctl identity status
clusterctl identity apply
```

Private delivery and receipt commands:

```bash
clusterctl bundle publish NODE SERVICE --generation N --source PATH --target-path PATH
clusterctl receipt write --node NODE --service SERVICE --generation N --status node-activated
clusterctl receipt collect NODE SERVICE --generation N
```

Deploy wrapper:
#TODO: I wnat i clusterctl deploy all
```bash
clusterctl deploy HOST --dry-run
clusterctl deploy HOST
```

## Editing SOPS Ledgers

Private identity material is edited by leaders:

```bash
nix run .#sops -- inventory/keys/identities/cluster-private-identities.sops.yaml
nix run .#sops -- inventory/keys/followers/host-age-private-keys.sops.yaml
```

After changing public facts, timestamps, or delivery metadata:

```bash
clusterctl identity publish
```

Leaders also run a best-effort publish during NixOS activation when
`my.clusterIdentity.autoPublishOnActivation` is enabled. This keeps normal
leader rebuilds aligned with the rule that the flake is source truth and the
registry is the live projection.

## Rollout Sequence

### 1. Build And Check From A Leader

```bash
cd /work/flake
git status --short
nix flake check
nix build .#nixosConfigurations.r640-0.config.system.build.toplevel
nix build .#nixosConfigurations.desktoptoodle.config.system.build.toplevel
nix build .#nixosConfigurations.t320-0.config.system.build.toplevel
```

### 2. Deploy First Leader

Start with `r640-0` unless there is a reason to use `desktoptoodle`.

```bash
sudo nixos-rebuild switch --flake .#r640-0
```

Check:

```bash
systemctl status cluster-identity-fetch.timer
systemctl status cluster-identity-fetch.service
cat /etc/cluster-identity/policy.json
echo "$SOPS_AGE_KEY_FILE"
```

Leader activation should also attempt:

```bash
clusterctl --flake /work/flake identity publish
```

### 3. Initialize The Registry

```bash
sudo mkdir -p /var/lib/cluster-identity/registry
sudo chown root:root /var/lib/cluster-identity/registry
sudo clusterctl registry init --registry /var/lib/cluster-identity/registry
sudo clusterctl registry validate --registry /var/lib/cluster-identity/registry
sudo clusterctl registry reconcile \
  --registry /var/lib/cluster-identity/registry \
  --out /run/cluster-identity
```

### 4. Add Remotes

```bash
cd /var/lib/cluster-identity/registry
git remote -v
git remote add radicle RADICLE_REMOTE_HERE || true
```

Add Yggdrasil and fallback leader remotes as they become available.

### 5. Publish Initial Identities

```bash
clusterctl identity publish
```

The default publisher reads `inventory/identities.nix`, emits missing signed
registry events for the whole ledger, reconciles state, and pushes configured
registry remotes.

Narrow publishes are available for debugging:

```bash
clusterctl identity publish --node r640-0
clusterctl identity publish --service yggdrasil
```

### 6. Deploy Other Nodes

Use existing deploy paths first:

```bash
nix run .#deploy-rs -- .#desktoptoodle
nix run .#deploy-rs -- .#t320-0
```

Or:

```bash
nix run .#colmena -- apply --on desktoptoodle
```

### 7. Fetch On Followers

```bash
clusterctl registry notify
```

On a follower:

```bash
systemctl status cluster-identity-fetch.timer
systemctl start cluster-identity-fetch-now.service
ls -R /run/cluster-identity
```

### 8. Test Deploy Resolution

```bash
clusterctl deploy r640-0 --dry-run
clusterctl deploy desktoptoodle --dry-run
clusterctl deploy t320-0 --dry-run
```

The dry run should show:

- active live registry target when present
- staged target when available for leader/deploy mode
- deprecated fallback when available for repair mode
- host-bootstrap fallback target
- selected target

## Deploy Resolution

`clusterctl deploy HOST --dry-run` should resolve candidates in this order:

```text
1. active Yggdrasil address from /run/cluster-identity
2. staged address in leader/deploy mode
3. deprecated address in repair mode
4. hostBootstrap.targetHost
5. plain host name
```

The deploy wrapper is additive. It should not remove or replace existing flake
outputs:

```bash
nix run .#deploy-rs -- .#HOST
nix run .#colmena -- apply --on HOST
```

## Private Delivery MVP

USB and PXE delivery are deferred.

For the first version, a leader can copy private material over root SSH:

```bash
clusterctl bundle publish r640-0 yggdrasil \
  --generation 2 \
  --source /tmp/r640-0-yggdrasil-private.key \
  --target-path /var/lib/yggdrasil/private.key
```

Expected behavior:

- copy private file to the target over SSH
- install it as root-owned `0400`
- write a local receipt on the target
- start `cluster-identity-fetch-now.service`
- let the leader collect and commit the receipt

Receipt collection:

```bash
clusterctl receipt collect r640-0 yggdrasil --generation 2
```

Promotion:

```bash
clusterctl identity promote r640-0 yggdrasil --generation 2
clusterctl registry push
clusterctl registry notify
```

Future private delivery should become age-encrypted bundles generated from the
SOPS private service identity ledger. Small host-targeted bundles should live
under registry `bundles/` with signed manifests. Large or frequently rotated
material can move to a content-addressed external store later.

## Documentation Requirements

Implementation must update operator docs and dendrite-local docs.

Required docs:

```text
docs/cluster-ops/identity/README.md
docs/cluster-ops/identity/registry/live-identity-registry.md
docs/cluster-ops/identity/registry/identity-registry-transport.md
docs/cluster-ops/identity/operations/identity-rollout-playbook.md
docs/cluster-ops/identity/operations/identity-registry-troubleshooting.md
dendrites/system/dendrites/cluster-identity/README.md
README.md
```

The dendrite README must include:

- module options
- files created
- systemd units
- expected registry path
- expected materialized path
- SOPS age key behavior
- interaction with SSH, Yggdrasil, Radicle, and git-annex
- what the dendrite does not do
- manual testing commands
