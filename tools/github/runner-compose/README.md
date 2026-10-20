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
