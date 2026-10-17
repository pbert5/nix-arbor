# Repository-scoped GitHub Actions runners

`./tools/github/runners` manages one runner per **private** GitHub repository
through its own Compose project and named `runner-state` volume. It uses the
existing Docker Engine and `/mypool/docker_data`; it does not configure
NixOS, create a registry, change other Compose projects, or remove volumes.

```sh
./tools/github/runners enroll --repo pbert5/meta_bal
./tools/github/runners up --repo pbert5/meta_bal
./tools/github/runners status --repo pbert5/meta_bal
./tools/github/runners logs --repo pbert5/meta_bal
./tools/github/runners rebuild --repo pbert5/meta_bal
./tools/github/runners up-up --repo pbert5/meta_bal
./tools/github/runners doctor --repo pbert5/meta_bal
./tools/github/runners down --repo pbert5/meta_bal
```

`rebuild` is an idempotent normal start. `up-up` rebuilds the pinned official
Actions runner (`2.338.0`, SHA-256 verified) without cache and recreates only that repository's
runner container. Both preserve the named volume. `down` stops the service and
keeps registration state; no command prunes Docker or deletes a volume.
Project names are `nix-arbor-runner-<owner>-<repo>-<id>`, with a short
repository hash to keep normalized names unique. Repositories do not share
credentials or Compose state.

Enrollment requires `gh auth login` with permission to create repository
runner registration tokens, or a one-time token entered at a hidden prompt.
The tool checks that the repository is private, asks for confirmation, and
streams the short-lived registration token to a one-shot container over stdin.
It does not put a PAT or registration token in container environment, Compose
configuration, logs, or the host repo. GitHub's runner-specific lifecycle
credentials and identity files persist in the mode-restricted named volume;
they are the credentials needed for that registered runner to reconnect.
The host-side per-repository config under
`${XDG_CONFIG_HOME:-~/.config}/nix-arbor/runners/` contains repository, labels,
runner name and pinned version only.

The runner has no host Docker socket, privileged mode, host mounts, or
Docker-in-Docker daemon. It is still a container on the physical host, **not a
VM security boundary**. A job can access the runner's private repository
registration and its job workspace, and a container escape would reach the
host. Do not schedule public fork code, untrusted pull requests, or untrusted
workflow revisions here. Consumer workflows must explicitly gate runner use
to trusted events, refs and actors before adding these labels. No consumer
workflow is switched by this tool. `R640_CI_READY` stays unset until a trusted
job is observed succeeding.

Docker-dependent jobs are unsupported by the default runner. Host-socket
mounting would grant host-root-equivalent control. Privileged Docker-in-Docker
is also a material privilege escalation and is not configured here. Keep such
jobs on GitHub-hosted runners until a separately reviewed runtime is approved.

The runner uses `restart: unless-stopped`, so Docker restarts it after host
reboot and container recreation reuses registration state. The version is
pinned in the Compose tool; update it deliberately and run `up-up` to refresh.
Use `status` to compare the local container with GitHub's repository runner
API and `doctor` for local configuration and security reminders.
Starting an enrolled service also rechecks that GitHub still reports the
repository as private. `status` and `doctor` display a warning when that check
cannot be completed.

Validation:

```sh
bash -n tools/github/runners tools/github/runner-compose/cli \
  tools/github/runner-compose/entrypoint.sh tests/github/runners-contract.sh
bash tests/github/runners-contract.sh
bash tests/github/runners-compose-smoke.sh
docker compose --project-name runners-config-check \
  --env-file tests/github/runners.compose.env \
  -f tools/github/runner-compose/compose.yaml config --quiet
```
