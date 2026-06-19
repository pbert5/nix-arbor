> Status: historical seed plan.
>
> The registry design from this seed plan has been promoted into
> `docs/cluster-ops/identity/registry/`,
> `docs/cluster-ops/identity/operations/`, and
> `dendrites/system/dendrites/cluster-identity/README.md`. Historical plan notes
> were moved to `plans/registry/deprecated/`. In current behavior, the flake plus
> SOPS ledgers are the source of truth, the registry is the live projection,
> leaders publish from the flake, and signed encrypted bundle manifests remain
> planned work.

perfect, now make a plan for an egent to implement from a leader,  its realy importamt that it has full docs and play by play guides that are both in docs and info thats in the dendrites ( dont worry about the usb stuff yet for now we will just transport the private age keys over through ssh or whatever we have root for everything)  we want: 
this part ok, for the transport layer, would it be best to have it as git remotes over ssh yig and raddicle + fall back ssh path: where everyone pulls from the leaders and radicle on a timer  and where leaders push to radicle on a timer
in addition those relevent events can be triggered when a leader adds to the registry ( throguh clusterctrl opperations that would commit changes on sucesss)  then tell the other nodes to pull and then they would see the change and implement

and the following  that you had described:
Yes. This is probably the right direction.

The clean version is:

```text id="jik2uh"
Keep slow, structural config in the flake.

Move fast-changing cluster identity facts into a live signed identity registry.

Leaders write to it.

Everyone reads it.

Nodes do not need a rebuild just to learn that r640-0 now has a new Yggdrasil address, SSH host key, Radicle NID, or git-annex endpoint.
```

That directly solves the fragility you are worried about: if Yggdrasil identity changes, the deployer should not need a rebuild before it can discover the new address.

Your repo already has the right place to attach this because it is inventory-driven: `inventory/` owns hosts, networks, roles, storage, and other site facts, while `lib/` handles normalization, assembly, validation, and deployment surfaces . You also already have `inventory/host-bootstrap.nix` as a separate bootstrap/deployment data layer , with fields like `deploymentTransport`, `identityFile`, `operatorCapable`, `sshUser`, and `targetHost` . So this does not fight your architecture.

# New model

## Flake

The flake defines:

```text id="l9n70q"
host roles
service modules
hardware config
expected identity policy
who the leaders are
where the live registry is mounted/synced
which services consume live identity data
fallback bootstrap paths
```

The flake does **not** need to contain every current Yggdrasil address or current SSH host key as the only usable source of truth.

## Live identity registry

The live registry defines:

```text id="0vwutv"
current public identity for each service on each node
deprecated fallback identities
burned/compromised identities
pending private identity deliveries
signed leader update records
receipt/ack records from target nodes
```

## Leaders

Leaders can:

```text id="i4fyly"
write signed identity updates
encrypt private identity bundles to a target node
mark old identities deprecated
mark compromised identities burned
promote pending identity to active after receipt
```

## Followers

Followers can:

```text id="li7o0c"
read registry updates
verify leader signatures
update local /run or /var cache
use active identity records for routing/contact
ignore unsigned or stale records
ack receipt of private bundles intended for themselves
```

# Important correction: do not use plain “newest wins”

Your “most recently generated one wins” instinct is close, but I would not base it on wall-clock timestamps alone.

Use:

```text id="x60w4e"
subject + service + monotonically increasing generation
```

Example identity subject:

```text id="zsj6dr"
node: r640-0
service: yggdrasil
generation: 12
state: active
```

Then the rule is:

```text id="kk36hf"
For each node/service, accept the highest valid generation signed by an authorized leader, unless that generation or key is burned.
```

Do **not** rely only on timestamps because clocks drift and old leaders can replay stale updates. You can still include timestamps, but they should be metadata, not the deciding authority.

Better ordering:

```text id="hp2uma"
1. burned/compromised always wins over active/deprecated
2. higher generation wins
3. leader signature must be valid
4. update must be within the allowed leader epoch
5. optional: require target receipt before active
```

# Registry structure

I would make this a separate repo or separate data directory:

```text id="5vdfk1"
cluster-identity-registry/
  registry/
    nodes/
      r640-0/
        ssh-host.json
        yggdrasil.json
        radicle.json
        git-annex.json
        age-recipient.json

    public/
      leaders.json
      policy.json
      burned.json

  private-delivery/
    r640-0/
      gen-012.bundle.age
      gen-012.manifest.json

  log/
    00000001-r730-leader-01.json
    00000002-r730-leader-01.json
    00000003-desktoptoodle.json

  receipts/
    r640-0/
      gen-012-yggdrasil.receipt.json
```

But for simplicity, I’d probably start with one append-style event log plus a generated materialized view.

```text id="ip8unh"
events/      append-only signed updates
state/       generated current view
bundles/     encrypted private delivery bundles
receipts/    node acknowledgements
```

# Event format

Example public identity update:

```json id="8guf4z"
{
  "schema": "cluster.identity.event.v1",
  "eventId": "01HX...",
  "leader": "r730-leader-01",
  "leaderKey": "ssh-ed25519 AAAA...",
  "subject": {
    "node": "r640-0",
    "service": "yggdrasil"
  },
  "generation": 12,
  "state": "staged",
  "public": {
    "yggdrasilPublicKey": "abc123",
    "yggdrasilAddress": "200:...",
    "deployHost": "200:..."
  },
  "privateDelivery": {
    "bundle": "bundles/r640-0/yggdrasil-gen-012.age",
    "encryptedTo": [
      "age1-current-node-recipient",
      "age1-deprecated-node-recipient"
    ],
    "requiresReceipt": true
  },
  "supersedes": [
    11
  ],
  "createdAt": "2026-05-07T00:00:00Z",
  "signature": "..."
}
```

Example burn record:

```json id="uf8v15"
{
  "schema": "cluster.identity.event.v1",
  "eventId": "01HY...",
  "leader": "r730-leader-01",
  "subject": {
    "node": "r640-0",
    "service": "yggdrasil"
  },
  "generation": 11,
  "state": "burned",
  "reason": "suspected compromise",
  "createdAt": "2026-05-07T00:05:00Z",
  "signature": "..."
}
```

Example receipt:

```json id="x4uzj4"
{
  "schema": "cluster.identity.receipt.v1",
  "node": "r640-0",
  "service": "yggdrasil",
  "generation": 12,
  "status": "received-private-bundle",
  "activated": true,
  "observedPublic": {
    "yggdrasilAddress": "200:..."
  },
  "signedByNode": "ssh-ed25519 AAAA...",
  "createdAt": "2026-05-07T00:10:00Z",
  "signature": "..."
}
```

# State machine

Use this:

```text id="45ie9z"
planned
  ↓
staged-public
  ↓
private-delivered
  ↓
node-received
  ↓
node-activated
  ↓
leader-verified
  ↓
active
  ↓
deprecated
  ↓
removed

Compromise path:
  any state → burned
```

The important thing:

```text id="9zjjcz"
Public identity can be visible before it is active.

Private identity can be delivered before everyone starts using the new public identity.

Active should only happen after receipt or verification.
```

That solves your concern at the end: best behavior is **confirmation of receipt before everyone switches**.

# How the rollout works

## Rotate Yggdrasil identity for `r640-0`

### 1. Leader generates new Yggdrasil identity

Leader creates:

```text id="jpcwse"
new yggdrasil private key
new public key
new Yggdrasil address
generation 12
```

### 2. Leader writes staged event

The live registry gets:

```text id="rzl6n4"
r640-0/yggdrasil gen12 staged-public
```

Everyone can see the public identity, but they do not use it as primary yet.

### 3. Leader encrypts private bundle

Bundle encrypted to:

```text id="ad2mon"
r640-0 current age recipient
r640-0 deprecated age recipients, if they are allowed repair paths
optional temporary bootstrap recipient
```

This is the key part of your idea: the private bundle is not baked into every machine’s Nix build. It is just a live delivery object.

### 4. Target node sees bundle

`r640-0` sees:

```text id="9lm3vm"
There is a private bundle for me.
I can decrypt it.
It contains my new Yggdrasil identity.
```

It installs it into something like:

```text id="kow09l"
/var/lib/cluster-identity/services/yggdrasil/gen-012/private.key
```

### 5. Node acknowledges

It writes a receipt:

```text id="2y86z7"
I received gen12.
I activated gen12.
My observed address is 200:...
```

Signed by the node.

### 6. Leader verifies

Leader checks:

```text id="jxqecp"
Can I reach r640-0 at gen12 Ygg address?
Does the SSH host key match expected?
Does the node report gen12 active?
```

### 7. Leader promotes

Leader writes:

```text id="4fxbf8"
r640-0/yggdrasil gen12 active
r640-0/yggdrasil gen11 deprecated
```

Everyone now starts using gen12 as primary, with gen11 optionally available as fallback.

### 8. Later leader burns or removes old one

After confidence:

```text id="u9rbze"
gen11 removed
```

If compromised:

```text id="5y2lk3"
gen11 burned
```

Burned means never use again, even if an old leader publishes a stale deprecated record.

# How nodes consume it

Each node runs a small service:

```text id="4vfgby"
cluster-identity-agent
```

It does:

```text id="xrxi86"
sync registry
verify leader signatures
materialize current state into /run/cluster-identity
install private bundles intended for itself
write receipts
reload services when their identity changes
```

Example generated files:

```text id="g0oxu5"
/run/cluster-identity/active/r640-0/yggdrasil.json
/run/cluster-identity/active/r640-0/ssh-host.json
/run/cluster-identity/deprecated/r640-0/yggdrasil.json
/run/cluster-identity/burned/r640-0/yggdrasil.json
```

Then deployment tooling reads from `/run/cluster-identity`, not from the flake.

# How deploy-rs / Colmena fit

Your current deployment generation resolves targets from inventory, bootstrap, and private Yggdrasil network info in `lib/deployments.nix` . Keep that as the static fallback.

But for live deployment, wrap deploy-rs/Colmena with your own resolver:

```bash id="mr4kpc"
clusterctl deploy r640-0
```

It does:

```text id="fgoap1"
1. Ask live registry for r640-0 active deploy endpoint.
2. Try active Yggdrasil address.
3. If that fails, try staged address if leader-visible.
4. If that fails, try deprecated repair addresses.
5. If that fails, try host-bootstrap targetHost.
6. Then call deploy-rs or Colmena with the chosen target.
```

So deploy-rs still deploys a NixOS system, but it no longer needs to know every possible identity fallback at flake evaluation time.

# What stays in the flake

Your flake should keep only the policy and defaults:

```nix id="6tafw9"
{
  cluster.identity = {
    enable = true;

    registry = {
      mode = "syncthing"; # later: git, radicle, seaweedfs, nfs, etc.
      path = "/var/lib/cluster-identity/registry";
      materializedPath = "/run/cluster-identity";
    };

    leaders = [
      "r730-leader-01"
      "desktoptoodle"
    ];

    trustedLeaderKeys = {
      "r730-leader-01" = "ssh-ed25519 AAAA...";
      "desktoptoodle" = "ssh-ed25519 AAAA...";
    };

    policy = {
      requireReceiptBeforePromote = true;
      allowDeprecatedFallback = true;
      burnedAlwaysWins = true;
      maxDeprecatedFallbacks = 2;
    };
  };
}
```

And per-host:

```nix id="ux20q8"
org.clusterIdentity = {
  role = "leader"; # leader | follower | bootstrap-only

  services = {
    yggdrasil.enableLiveIdentity = true;
    ssh.enableLiveKnownHosts = true;
    radicle.enableLiveIdentity = true;
    gitAnnex.enableLiveIdentity = true;
  };
};
```

# What moves out of the flake

Move these out of required rebuild path:

```text id="72f4vg"
current Yggdrasil addresses
current public SSH host keys used for live contact
current Radicle NIDs
current git-annex endpoints
deprecated fallback addresses
pending identity delivery bundles
receipts and verification status
```

The flake can still contain initial seed values or expected policy, but the live registry is what machines actually consult.

# Do not use Syncthing as the trust layer

Syncthing is fine as a transport.

But the trust layer should be:

```text id="ej09bp"
leader signatures
node signatures for receipts
monotonic generations
burn records
local verification rules
```

So it should not matter whether the registry arrives over:

```text id="6jgzeq"
Syncthing
git pull
Radicle
SeaweedFS
NFS
rsync
HTTP
Yggdrasil file server
```

Transport is just distribution. The registry should be self-authenticating.

# Key compromise rules

You need explicit states:

```text id="0c5syc"
active
  primary identity

staged
  may be used by leaders for verification/deployment

deprecated
  allowed fallback if active fails

removed
  ignored, but not necessarily treated as hostile

burned
  never use, never resurrect, reject future records that try to reintroduce it
```

This solves your stale leader problem.

Rule:

```text id="pc9sve"
A burned key cannot be made active or deprecated by a later lower-authority or stale event.
```

To make that reliable, either:

```text id="qw6jfe"
burn events require same or higher generation
```

or better:

```text id="yrlnk6"
burn events are keyed by fingerprint and are globally absolute.
```

Example:

```json id="vqz8ry"
{
  "type": "burn",
  "fingerprint": "sha256:abc123",
  "reason": "compromised",
  "signedBy": "r730-leader-01"
}
```

Any identity containing that fingerprint is rejected forever unless you manually clear the burn list with a higher-security recovery action.

# Leader conflict rules

Since you may have multiple leaders, use one of these.

## Simple mode

For now:

```text id="23qz4f"
Any leader can write.
Highest generation wins.
Burned always wins.
Receipts required before active.
```

This is easiest.

## Better mode

Add leader epochs:

```text id="dz5z20"
leaderPolicyEpoch = 4
```

Every leader update includes the policy epoch. Nodes reject updates from old epochs.

This prevents an old leader config from reintroducing stale records.

## Best mode later

Require quorum for dangerous actions:

```text id="ahvff8"
1 leader signature for staged
1 leader signature + node receipt for active
2 leader signatures for burn removal
2 leader signatures for leader-policy change
```

You do not need this on day one.

# How private delivery works

Your idea is good:

```text id="lnepm5"
Secrets stored at rest can remain leader-encrypted or managed by leaders.

When delivering to a node:
  leader decrypts or generates private material locally
  leader re-encrypts the bundle to the node's current/deprecated/temp age recipient
  leader publishes the encrypted bundle into the live registry
  only that node can decrypt it
```

That means leaders do not need every node private age key.

A private bundle should be addressed like:

```json id="50mphk"
{
  "targetNode": "r640-0",
  "targetService": "yggdrasil",
  "generation": 12,
  "encryptedTo": [
    "age1-current",
    "age1-deprecated",
    "age1-temp-bootstrap"
  ],
  "payloadPath": "bundles/r640-0/yggdrasil-gen-012.age"
}
```

The node agent tries to decrypt bundles addressed to itself.

# The one key that still matters most

The node’s root decryption identity is still special.

Call it:

```text id="mnh6xd"
node root age identity
```

It should be stable and hard to rotate casually.

For rotating that, use the temporary bootstrap key system:

```text id="rg4jxt"
leader creates temp age keypair
temp private key goes via USB/PXE/ISO/manual
leader encrypts new node root age key to temp public key
node decrypts and installs new root age key
node writes receipt
leader promotes new age recipient
```

This fits your idea exactly.

# Integration into `flake-devbox`

I would implement this as a new dendrite plus tools.

## Add files

```text id="k0gf6q"
inventory/identity-policy.nix
inventory/identity-registry-bootstrap.nix

dendrites/system/dendrites/cluster-identity/
  cluster-identity.nix
  meta.nix

tools/clusterctl/
  clusterctl/main.py
  clusterctl/registry.py
  clusterctl/signing.py
  clusterctl/materialize.py
  clusterctl/deploy.py
  clusterctl/bundles.py

docs/cluster-ops/live-identity-registry.md
```

## `inventory/identity-policy.nix`

```nix id="8nskcw"
{
  registry = {
    path = "/var/lib/cluster-identity/registry";
    materializedPath = "/run/cluster-identity";
    transport = "syncthing";
  };

  leaders = {
    "r640-0" = {
      publicSigningKey = "ssh-ed25519 PLACEHOLDER";
      canWrite = true;
    };

    "desktoptoodle" = {
      publicSigningKey = "ssh-ed25519 PLACEHOLDER";
      canWrite = true;
    };
  };

  policy = {
    requireReceiptBeforePromote = true;
    burnedAlwaysWins = true;
    allowDeprecatedFallback = true;
    maxDeprecatedFallbackGenerations = 2;
  };
}
```

## Add to `inventory/inventory.nix`

```nix id="toxwi8"
identityPolicy = import ./identity-policy.nix;
identityRegistryBootstrap = import ./identity-registry-bootstrap.nix;
```

You already import inventory sections manually in that file, so this matches the current pattern .

## Dendrite behavior

`cluster-identity.nix` should:

```text id="6zzysl"
install cluster-identity-agent
configure registry path
configure trusted leader keys
materialize active identities into /run/cluster-identity
optionally manage live known_hosts
optionally expose systemd path units to reload services
```

Runtime outputs:

```text id="dz2xr4"
/run/cluster-identity/known_hosts
/run/cluster-identity/yggdrasil/peers.json
/run/cluster-identity/radicle/nodes.json
/run/cluster-identity/git-annex/remotes.json
```

# How this affects SSH

Instead of only static `known_hosts` from Nix rebuild, do:

```text id="opawz7"
Nix installs baseline trusted leader keys and agent policy.

Agent writes live known_hosts from signed registry:
  /run/cluster-identity/ssh_known_hosts

SSH config includes:
  UserKnownHostsFile /run/cluster-identity/ssh_known_hosts ~/.ssh/known_hosts
```

For root deployments:

```text id="06q97y"
clusterctl resolves target from live registry
clusterctl uses expected host key from live registry
clusterctl calls deploy-rs/Colmena with the resolved target
```

# How this affects Yggdrasil

Do not require rebuild to learn new peer/address facts.

Instead:

```text id="7smt1e"
Nix declares Yggdrasil is managed by cluster identity agent.

Agent writes:
  /run/cluster-identity/yggdrasil/peers.conf
  or a generated config fragment

Agent restarts/reloads Yggdrasil when active peer data changes.
```

For the node’s own private Yggdrasil key:

```text id="8mtstl"
Private key delivered by encrypted bundle.
Installed into /var/lib/yggdrasil/private.key.
Nix points Yggdrasil at that path.
```

So Nix still controls the service shape, but live registry controls the identity value.

# How this affects Radicle and git-annex

Use same pattern:

```text id="osf7cn"
Radicle:
  public NID/endpoints in registry
  private machine seed key in encrypted bundle

git-annex:
  repo UUID and endpoint metadata in registry
  credentials/private SSH material in encrypted bundle
```

For git-annex specifically, be careful not to rotate repository UUIDs unless the repo identity actually changes. Often you want to update access endpoints, not the annex UUID.

# Practical implementation sequence

## Step 1: Create the live registry format

Do this first, no service changes.

```text id="bw77ye"
docs/cluster-ops/live-identity-registry.md
tools/clusterctl/registry.py
```

Implement:

```bash id="ndtyx1"
clusterctl registry init
clusterctl registry validate
clusterctl registry materialize
```

## Step 2: Add leader signing

Use a simple signing key first. SSH signing is fine.

Commands:

```bash id="n5d8tx"
clusterctl identity publish-public r640-0 yggdrasil --generation 1 --state staged
clusterctl registry verify
```

## Step 3: Add materialized active view

Generate:

```text id="tngzut"
state/active.json
state/deprecated.json
state/burned.json
```

Nodes can consume these without parsing the whole event log.

## Step 4: Add NixOS dendrite

Add the agent and config paths. Do not yet reload critical services automatically.

## Step 5: Add SSH known_hosts live materialization

This is the safest first consumer.

```text id="aljn4u"
Registry event → materialized known_hosts → clusterctl deploy uses it
```

## Step 6: Add Yggdrasil endpoint consumption

Then update deploy resolver to use live Ygg addresses.

## Step 7: Add private bundle delivery

Add:

```bash id="nekr1q"
clusterctl bundle create r640-0 yggdrasil --generation 2
clusterctl bundle publish r640-0 yggdrasil --generation 2
clusterctl bundle receive
```

## Step 8: Add receipt-based promotion

Do not skip this.

```bash id="5r83e7"
clusterctl identity promote r640-0 yggdrasil --generation 2
```

Promotion should fail unless:

```text id="e3nf5o"
bundle receipt exists
node activated it
leader can verify reachability
no burned key conflict exists
```

# Final answer

Your new design is better than keeping all public identity data in the flake.

The strongest version is:

```text id="3eyfep"
Flake:
  defines identity policy, leaders, services, bootstrap defaults, and where the registry lives.

Live signed identity registry:
  defines current/staged/deprecated/burned identities.

Leaders:
  write signed public identity updates and encrypted private delivery bundles.

Nodes:
  read the registry, verify signatures, decrypt only bundles meant for them, write receipts, and update local live identity files.

Deployment tools:
  resolve targets from the live registry first, then fall back to flake/bootstrap targets.

Promotion:
  requires receipt/verification before everyone treats the new public identity as active.
```

This gives you what you want: Yggdrasil-first deployment without the nightmare of needing to rebuild everyone just to learn where one node moved.




make sure it fits with my flake-dev repo
