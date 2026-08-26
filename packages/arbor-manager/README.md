# Arbor Manager

Arbor Manager is the reusable assembly layer between a machine source and
ordinary NixOS configurations. `mkMachines` consumes pure source entries, so
callers can provide records from any source without adding a registry
dependency.

Its public API is `lib.mkMachines`:

```nix
inputs.arbor-manager.lib.mkMachines {
  inherit inputs;
  sources = [
    {
      name = "server";
      record = { system = "x86_64-linux"; profiles = [ "server" ]; };
      provenance = { kind = "registry-snapshot"; revision = "..."; };
      precedence = 10;
    }
  ];
  profiles = { server = [ ./profiles/server.nix ]; };
}
```

Each source entry has `name` and `record`, and may provide `modules`,
`provenance`, and numeric `precedence`. Records retain `cluster` (including
any relationship fields) as data; Arbor Manager does not prescribe role
values. `localSource ./config/machines` adapts the conventional directory
layout, and `registrySnapshot { digest = "sha256:..."; machines = { name = record; }; }`
adapts an immutable accepted snapshot. Registry snapshot entries contribute
public data only; trusted executable modules are selected by local composition.
The optional `hardware` field must contain exactly one data-only form:

```nix
hardware.snapshot = {
  format = "arbor/hardware";
  version = 1;
  facts = { memoryBytes = 17179869184; cpu = "x86_64-v3"; };
};
# or hardware.artifact = {
#   digest = "sha256:<64 lowercase hex characters>";
#   mediaType = "application/vnd.arbor.hardware+json";
# };
```

Hardware artifacts are references only; Arbor Manager does not fetch or
evaluate them. `hardware.modules` and executable values are rejected. Local
`hardware-configuration.nix` and `configuration.nix` modules remain explicit
members of a local source.

`sourceMerge` combines `registrySnapshot`, `committedLocal`, and an optional
`sessionOverride` per machine field. The result has `sources`, `machines`, and
a deterministic `digest`; each merged field records its layer and original
provenance. Session overrides may use only named `trustedLocalModules` via
`moduleSelectors`. Authority and identity-generation fields cannot be changed,
and duplicate names within a source are rejected.

## Machine and deployment snapshots

`lib.snapshot` provides pure inspection and export helpers. `inspectMachine`
accepts a resolved `mkMachines` entry or a record and returns source and
per-field provenance. `exportMachine` and `exportDeployment` produce
deterministic canonical JSON, while `digest` hashes that JSON. Secret-like
fields, runtime strings, paths, functions, derivations, and functors become
`<redacted>` before serialization, so exports contain no executable Nix or
secret material. Registry snapshots remain immutable data inputs: they supply
no modules; trusted executable code comes only from local composition.

For compatibility, `machinesPath = ./config/machines` remains an alias for
the local adapter. Local directories contain `default.nix` (facts), and may
contain `hardware-configuration.nix` and `configuration.nix` modules.
Directories are discovered deterministically in lexical order. Each result is
still assembled with native `nixosSystem`, with the normalized record exposed
at `config.arbor.machine` and as the `machine` special argument.

## Selection and deployment plans

The pure `lib.graph` function normalizes a node attrset whose optional
`children` and `parents` fields contain node names. `lib.selectors` provides
`local`, `children`, `descendants`, `parents`, `ancestors`, `peers`, and
`accessible`; all results are sorted and cycle-safe. `lib.select` returns the
selected names plus deterministic exclusion records. Nodes with
`reachable = false`, `compatible = false`, disabled nodes, and suspended or
standby nodes (unless explicitly allowed) are excluded with stable reason
strings.

`lib.plan` turns a selection into an inspectable deployment plan. It includes a
canonical snapshot and SHA-256 digest, backend recommendation (`direct` or
`colmena`), critical-route and state risks, canary/batch phases, acknowledgement
digest, and copyable names/commands. Selected names are emitted in graph order;
parents in the selected graph always precede their children, while unreachable,
incompatible, disabled, standby, and suspended targets remain excluded unless
their respective policy allows them. A canary is one first graph-valid node,
and the remaining nodes are partitioned into deterministic batches. The backend
strings are interfaces until an operator explicitly supplies a backend adapter
executable to the CLI. The Nix library still never opens connections or
executes Colmena.

When a plan selects the Colmena backend, `lib.rawHive` projects the same
resolved machine records into a raw Colmena hive. Only `plan.names` become
nodes, so exclusions and an empty plan never imply apply-all. Node records may
provide `targetHost`, `targetPort`, `targetUser` (or a `target` attrset) and
`tags`; these become Colmena deployment metadata. `mkMachines` exposes
`colmenaRawHive`, `colmenaSelection`, and `colmenaHive` only when its `inputs`
contains a Colmena flake input. `colmenaHive` calls that input's `lib.makeHive`
purely; it does not execute deployment.

## Offline CLI

The `arbor-manager` package and app provide inspection without evaluating a
machine configuration or connecting to a host. They accept the immutable JSON
written by `lib.snapshot.deploymentSnapshot`; the wrapper digest and embedded
`snapshotDigest` are verified before any output is produced.

```console
$ nix run .#arbor-manager -- nodes list --snapshot deployment.json --scope selected
api
$ nix run .#arbor-manager -- machine inspect --snapshot deployment.json --name api
$ nix run .#arbor-manager -- machine export --snapshot deployment.json --name api --format json
$ nix run .#arbor-manager -- deployment-plan --snapshot deployment.json --format text
$ nix run .#arbor-manager -- deployment plan --snapshot deployment.json --format text
```

`nodes list` supports `all`, `local`, `selected`, `excluded`, `roots`,
`children`, `descendants`, `parents`, `ancestors`, `peers`, and `accessible`
scopes. Formats are `table`, `names`, `json`, `ssh`, and `colmena`; JSON is
the default. `ssh` and `colmena` are display projections; execution remains an
explicit operator-supplied adapter. Inspection and planning remain offline.
`deployment plan` and `deployment apply --dry-run`
only display the immutable plan. A real `deployment apply` requires the digest (or
token) in the deployment snapshot and an explicit backend executable:

```console
$ nix run .#arbor-manager -- deployment apply --snapshot deployment.json \
    --acknowledgement <digest> --backend-executable ./my-deployer
```

The adapter is invoked once per node in each immutable plan phase, in phase
order, with no shell interpretation. It receives JSON on stdin containing the
selected backend (`direct` or `colmena`), snapshot and acknowledgement digests,
phase, node, risk, and endpoint metadata
(`targetHost`, `targetPort`, and `targetUser`, with `hostname` as the host
fallback). It must return a JSON object on stdout and use exit status zero for
success. The CLI returns structured per-node results and treats a non-zero exit
or invalid JSON as a failed node. It verifies the wrapper and snapshot digests,
immutable plan phases, and acknowledgement before starting; phase names must
be unique members of `snapshot.selected`. If no backend executable is
supplied, apply retains an explicit refusal with exit status 3. For a Colmena
plan, the adapter is the operator-supplied wrapper that turns these verified
requests into the desired `colmena apply` invocation; Arbor Manager does not
treat Colmena as registry truth. No SSH or Colmena networking is built into the
CLI. `--receipt FILE` writes resumable per-node results after each attempt;
`--resume FILE` accepts only a receipt authenticated with the local
`ARBOR_MANAGER_RECEIPT_KEY` and bound to the same snapshot and acknowledgement
digests. Receipt use requires that key to be set; keep it private and stable
across retries.

```nix
plan = lib.plan {
  nodes = inventory;
  roots = [ "api" ];
  selector = "accessible";
  batchSize = 2;
};
```
