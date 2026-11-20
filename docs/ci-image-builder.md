# Isolated OCI image builder

Nix Arbor provides a reusable workflow at
`.github/workflows/ci-build-images.yml`. It builds images on the repository's
opt-in WS-A MicroVM runner. Each guest has its own Docker daemon and bounded
CPU, memory, and disk. The build uses a BuildKit container inside that guest;
it does not use the physical host Docker socket.

Call the workflow only from a protected trusted branch. The workflow rejects
pull request events, mismatched caller repositories, non-protected refs, short
source revisions, unapproved registry hostnames, and malformed inventories.
Separate registry reader and writer credentials are passed as `workflow_call`
secrets and are never written to a derivation, checkout, image build argument,
or committed file. Only non-secret build arguments are allowed. Do not pass
secret values through Docker build arguments or build contexts.

The workflow checks out its own producer repository at the exact reusable
workflow commit reported by `job.workflow_repository` and `job.workflow_sha`.
It stages only the trusted validation/evidence schema files in runner temporary
storage, verifies the checked out SHA, and removes that producer checkout
before building. Consumer repositories need only provide their manifest and
Dockerfiles; they do not need to copy Nix Arbor schema files.

## Consumer inventory

Each consumer repository owns a JSON inventory beside its Dockerfiles. Keep
only images built from that repository; Compose images supplied by a vendor
are not rebuilt. Example:

```json
{
  "schemaVersion": 1,
  "repository": "pbert5/example",
  "images": [
    {
      "name": "service",
      "context": ".",
      "dockerfile": "Dockerfile",
      "platforms": ["linux/amd64"],
      "buildArgs": {}
    }
  ]
}
```

The initial source audit read the repositories' current default branch Compose
files on 2026-10-15. These are discovery snapshots, not permanent pins; the
consumer workflow must use the exact commit checked out by the build job and
keep its inventory in the same repository revision.

| Repository revision | First-party Compose build inputs | Vendor images excluded |
| --- | --- | --- |
| `pbert5/simple-evolver@3cfe0f1050a8ff45fc2f419fe0a0527744c619aa` | `Dockerfile` (shared by several services), `lifecycle.Dockerfile`, `tools/database-image/Dockerfile`, `tools/observability-image/Dockerfile`, `tools/observability-image/grafana/Dockerfile`, `integrations/node-red/Dockerfile`, `apps/operator-webui/Dockerfile`, `integrations/pgadmin/config-init.Dockerfile`, and custom Alloy, Loki, Tempo, Prometheus, and volume-exporter Dockerfiles under `tools/observability-config/` | Timescale/PostgreSQL is built from the repository's database image; no vendor Compose `image:` service was selected as a build input. |
| `pbert5/meta_bal@1f2ab8da2c95c0ade0830098f53a6c88bdf49e32` | `deploy/evolver-edge/compose.yaml` and `compose.dev.yaml` build the repository's `evolver/evolver-hardware` and `evolver/evolver-controller` contexts | `deploy/postgres-acceptance/compose.yaml` has no build context; devcontainer image is not a runtime image. |
| `pbert5/meta_webui_demo@c3fbee3ce0db57a897da0045f024f6a97119f468` | Root `Dockerfile` builds `meta-webui-interface`; `applications/demo-external/service/Dockerfile` builds `external-demo`; `docker/Dockerfile.chrome-devtools-mcp` is development tooling | Nginx, Postgres, pgAdmin, and CloudBeaver are vendor images and remain external pulls. |

The consumer owner chooses which discovered inputs belong in the trusted
prebuild inventory. In particular, development-only and hardware-control
images require the consumer's existing trust and runtime policy; discovery
does not authorize their publication or deployment.

`name` is a lowercase OCI path component. Contexts and Dockerfiles are relative
to the checkout and must remain inside it. The inventory is capped at 32 image
entries per workflow run. `linux/amd64` is required so a successful run always
proves an x86_64 build. Non-secret settings that affect image output may be
listed in `buildArgs`; names containing `secret`, `token`, `password`,
`credential`, `key`, `auth`, `bearer`, `passphrase`, `certificate`, or
`private-key` are rejected. Argument names use uppercase letters, digits, and
underscores, matching conventional Docker `ARG` names. Keep build arguments public and constant in the
tracked manifest; runtime credentials belong in BuildKit secret mounts in a
consumer-owned build design, which this shared workflow deliberately does not
provide.

The repository workflow passes the exact identity and manifest explicitly:

```yaml
jobs:
  prebuild:
    uses: pbert5/nix-arbor/.github/workflows/ci-build-images.yml@<reviewed-nix-arbor-commit>
    with:
      repository: pbert5/example
      manifest: ci/images.json
      runner_label: example
      registry_host: r640-0.<tailnet-DNS-suffix>.ts.net:8443
      verify_cache: false
    secrets:
      registry_reader_username: ${{ secrets.PRIVATE_REGISTRY_READER_USERNAME }}
      registry_reader_password: ${{ secrets.PRIVATE_REGISTRY_READER_PASSWORD }}
      registry_username: ${{ secrets.PRIVATE_REGISTRY_WRITER_USERNAME }}
      registry_password: ${{ secrets.PRIVATE_REGISTRY_WRITER_PASSWORD }}
```

Configure those reader and writer secrets only for the protected
environment/branch after WS-I has verified the private HTTPS endpoint, ACLs,
and credentials. Never expose
them to public-fork or pull-request workflows. The workflow itself accepts
only `push` and `workflow_dispatch` on the configured protected branch.

## Names and evidence

The writer credential authenticates to port 8443 for pushes and cache writes;
the separate read-only credential authenticates to the HTTPS reader on port
443 for digest resolution and pulls. The workflow verifies the reader and
writer endpoints independently.

An artifact is published beneath the frozen registry artifact namespace as
`<writer>/ci/<owner>/<repository>/<full-40-character-source-SHA>/<image>:sha-<full-SHA>`.
BuildKit cache is separate at
`<writer>/buildkit/<owner>/<repository>/<image>:trusted-main`. Cache reads and
writes happen only in the protected trusted workflow. Do not add a pull-request
cache writer or mutable `latest` promotion. Consumers resolve the recorded
digest and use the read-only HTTPS endpoint on port 443.

For each image the run records source commit/tree, recursive submodule pins,
inventory hash, Dockerfile hash, build context, target platforms, cache ref,
artifact tag, and pushed digest. It reads the pushed manifest by digest and
pulls that immutable reference before returning success. BuildKit emits
provenance and an SBOM; the job summary and 90-day workflow artifact retain the
machine-readable evidence. These records establish source and digest linkage;
they are not a cryptographic signature.

The private registry does not enforce tag immutability. Before a push, the
workflow uses the authenticated registry API and refuses to continue on any
status other than a confirmed 404. It refuses to retarget an existing
source-SHA tag, verifies the post-push digest at the writer endpoint, and
resolves the same digest with the reader credential. All builds for a caller
repository share one concurrency group, so different source revisions cannot
write its moving `trusted-main` cache tags concurrently. Artifact tags still
include the full source SHA and remain separate. If a push or registry lookup fails, the
workflow fails without updating any consumer-facing mutable tag.

## Prewarm and recovery

Use `workflow_dispatch` on the protected branch to prewarm an approved image
revision. A normal protected-branch push can also run the consumer's prebuild
job. The workflow has a 90-minute bound and 32-image limit; schedule only the
consumer-selected images rather than rebuilding all historical commits. Set
`verify_cache: true` only on a targeted `workflow_dispatch` to build again with
a fresh BuildKit daemon, report the elapsed time and require at least one
`CACHED` step. This isolates the replay from the first daemon's local cache and
provides measured evidence that registry cache import works.

Rollback by reverting the consumer's workflow call or removing its runner and
registry secrets. This does not delete registry artifacts or caches. Pin a
consumer deployment to its previously recorded digest. Cache references are
disposable performance data; artifact retention and manual garbage collection
follow the registry operator procedure in `docs/private-oci-registry.md`.

Live HTTPS push/pull, cache hit measurements, and cross-VM pulls require WS-I
to complete the tailnet, ACL, credential, and separate-authorized-client
preflight. The workflow cannot claim those runtime checks before that work.
