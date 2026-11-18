# R640-0 GitHub Actions rollout

Each repository has its own GitHub Actions runner registration. The
`./tools/github/runners` CLI in Nix Arbor only enrolls **private**
repositories and uses a Docker Compose container with a persistent registration
volume. It does **not** mount the host Docker socket, run privileged, install
an OCI registry, or alter NixOS.

## Workflows added 2026-10-20

| Repository | Branch | `.github/workflows/r640-ci.yml` | Gate |
| --- | --- | --- | --- |
| `pbert5/simple-evolver` | `main`, `refine_webui` | Python CLI tests and frontend checks | Active; verified with real R640 jobs |
| `pbert5/meta_webui_demo` | `master` | Node frontend typecheck/unit/build | Repo variable `R640_RUNNER_READY=true` |
| `pbert5/meta_bal` | `master` | Docker-free repository and script smoke | Repo variable `R640_RUNNER_READY=true` |
| `pbert5/nix-arbor` | `main` | Manual shell/script smoke only | **Disabled** pending public-repo isolation |
| `pbert5/arbor-manager` | `main` | Manual CLI shell syntax smoke only | **Disabled** pending public-repo isolation |
| `pbert5/arbor-registry` | `main` | Manual Python compile smoke only | **Disabled** pending public-repo isolation |

All added workflows are either `push` on an explicitly approved branch or
`workflow_dispatch`; none has a `pull_request` or `pull_request_target`
trigger, and the jobs require `contents: read` and no credential persistence
from checkout. Existing hosted PR/test/release workflows are unchanged.
`R640_RUNNER_READY` is **per repository**, distinct from the earlier
`R640_CI_READY` OCI/VM integration marker.

## Enroll and turn on the private repositories

From the running `r640-0` host's Nix Arbor checkout, with an authenticated
GitHub CLI, enroll **one repo at a time**, verify it is online, and only then
enable that repo's Actions gate. The CLI prompts for a short-lived GitHub runner
registration token or requests one using the existing `gh` login.

```bash
cd ~/documents/nix-arbor
git pull --ff-only

./tools/github/runners enroll --repo pbert5/meta_webui_demo
./tools/github/runners status --repo pbert5/meta_webui_demo
./tools/github/runners doctor --repo pbert5/meta_webui_demo

./tools/github/runners enroll --repo pbert5/meta_bal
./tools/github/runners status --repo pbert5/meta_bal
./tools/github/runners doctor --repo pbert5/meta_bal
```

Confirm each exact runner is online with its labels, and check the private
repository's Actions fork-workflow policy. With no active untrusted PR access,
enable the gated workflows independently:

```bash
gh variable set R640_RUNNER_READY --repo pbert5/meta_webui_demo --body true
gh variable set R640_RUNNER_READY --repo pbert5/meta_bal --body true
```

These commands require repository permission to manage Actions variables;
the GitHub repository-content connector cannot provision runner tokens,
register local Docker containers or change Actions repository variables.
The scripts persist registration only to their own Docker volumes. Never put
registration tokens in an issue, file, workflow YAML or command argument.

Monitor Actions in each repository. The Meta WebUI R640 workflow tests its
frontend, **not** the whole Playwright/Compose release suite. The Meta BAL
R640 workflow is intentionally a **smoke**; full Server Dev Container and
PostgreSQL acceptance remain on existing GitHub-hosted workflows until a
separately reviewed Docker-in-Docker or guest isolation contract exists.
Expect no R640 CI work while `R640_RUNNER_READY` is absent or false: GitHub
will report those gated jobs as **skipped**, rather than queueing forever.

## Avoid redundant GitHub-hosted push failures when hosted minutes are exhausted

GitHub reports the status of **every** workflow that starts, even if a separate
R640 job on the same commit succeeded. There is no setting that makes a
self-hosted success override an unrelated failed hosted job. To avoid those
no-minute failures on approved *trusted branch pushes*, existing hosted jobs
now support a **separate explicit opt-out**. They continue to run for PRs and
when manually dispatched (`workflow_dispatch`), and they do not suppress
genuine self-hosted test failures.

Opt-out requires **both** of these per-repository Actions variables:
`R640_RUNNER_READY=true` AND `R640_SKIP_HOSTED_PUSH=true`. Absent/unset
values keep existing hosted push checks enabled, not silently disabled.

Only after the repository's R640 runner is verified online, and the relevant
self-hosted tests actually PASS, may an operator do:

```sh
gh variable set R640_RUNNER_READY -R pbert5/simple-evolver --body true
gh variable set R640_SKIP_HOSTED_PUSH -R pbert5/simple-evolver --body true
```

For Meta WebUI (`master`) and Meta BAL (`master`), substitute their
repository name. The ordinary opt-out affects only the hosted
`operator-webui.yml` jobs in Simple Evolver, `enforcement.yml` in Meta
WebUI, and `api-workbench.yml` in Meta BAL. It does **not** skip non-master
Meta WebUI/Meta BAL push jobs, e.g. Meta BAL `api-tui`, nor pull requests.

**Coverage is not equivalent yet**: Simple Evolver's current R640 workflow
does not run Playwright E2E; Meta WebUI's frontend-only workflow does not cover
all LinkML/Python/Playwright checks; Meta BAL's R640 job is only a repository
smoke and does **not** run Server Dev Container/Postgres acceptance. Leave
`R640_SKIP_HOSTED_PUSH` unset or false in a repo until you explicitly accept
that temporary coverage reduction or port the missing tests to a safe
self-hosted environment. Never claim that skipped tests passed.

Meta WebUI production `evolver-release.yml` and Meta BAL
`evolver-code-artifact.yml` are separately guarded by
`R640_SKIP_RELEASE_PUSH` and `R640_SKIP_ARTIFACT_PUSH`, respectively.
**Do not set these** until corresponding release/artifact verification runs
successfully elsewhere. Merely having the R640 frontend/smoke job pass is
not equivalent.

To re-enable hosted push checks in a repository without code edits:

```sh
gh variable set R640_SKIP_HOSTED_PUSH -R pbert5/simple-evolver --body false
```

These changes cannot retroactively turn earlier failed GitHub runs green.
Changing the repo variables requires GitHub permission to manage Actions
variables and the local authenticated `gh` CLI; the connected GitHub code
tool cannot set them. Hosted pull-request jobs may still fail because of
minute quota, and public/untrusted PR code must not be sent to the present
container-only runner to hide that failure. To resolve that case, fund
GitHub-hosted minutes or provide a separately isolated and policy-gated
self-hosted PR runner. Also review any *required status checks* in GitHub
branch protection: do not require hosted jobs that cannot execute, but do not
drop required tests without a genuinely equivalent protected check.

## Public Arbor repositories

`nix-arbor`, `arbor-manager`, and `arbor-registry` are public. The
current Compose enrollment tool **refuses public repositories**, intentionally.
Adding a manual, main-only, default-disabled workflow is not permission to
register a runner in a public repository. A malicious fork can change a
workflow to target exposed runner labels, bypassing filters in our own YAML.
Use an independently isolated, ephemeral guest/runner and review repository
Actions policies before enrolling or setting the public repositories' ready
variable. Until then, these are **staged workflow definitions**, not online
CI. Running `nix flake check` also requires a Nix-enabled environment; the
container workflow only checks available shell/Python sources.

## Verification and limitations

Runner labels for private repositories use
`[self-hosted, linux, x64, r640-0, docker-compose]`. Registrations are
repository-scoped, so an enrolled Simple Evolver runner cannot take Meta WebUI
or Meta BAL jobs even with identical labels. Each additional private repo
needs its own `enroll` and independent online verification.

Do not expose the physical Docker socket, use global `docker system prune`,
change the existing ZFS dataset, or claim the full CI/OCI platform is accepted
based on these basic workflows. Keep `R640_CI_READY` unset until its broader
original acceptance criteria have passed.

## Browser-only CI screenshots on R640

The runner image now includes the **system libraries** required by Playwright's headless Chromium on Ubuntu 24.04. It still runs as UID 1001, without sudo, host Docker access, privileged mode, or any attached lab hardware. The Playwright browser binary is downloaded into the runner user's cache by the consumer workflow, not baked into the image.

After this Dockerfile change is merged, refresh the actual Simple Evolver repository-scoped runner image on `r640-0`:

```sh
cd ~/documents/nix-arbor
git pull --ff-only
./tools/github/runners rebuild --repo pbert5/simple-evolver
./tools/github/runners status --repo pbert5/simple-evolver
```

Then rerun the `Blockly README previews` workflow on `code-block-refinements` and `refine_webui`, or push a new change to either branch's authoring WebUI. The workflow uses fixture-backed Blockly in headless Chromium and commits PNG snapshots to the same branch. A runner rebuild is required because an existing runner container does not gain newly declared OS packages until its image/container is recreated.
