# Meta BAL GitHub Actions runner

`r640-0` composes one repository-scoped runner for `pbert5/meta_bal` through
the native NixOS `services.github-runners` module.

Runtime contract:

- systemd unit: `github-runner-meta-bal.service`
- labels: `self-hosted`, `r640-0`, `meta-bal`, plus the default platform labels
- execution identity: `arbor-github-runner:arbor-github-runner`
- Docker access: explicit membership in the host `docker` group; this is
  root-equivalent access to the Docker daemon and is intentional for the
  repository's Dev Container workflow
- token path: `/var/lib/arbor-secrets/github-runners/meta-bal.token`

The token file is an operator-provisioned runtime secret. It must not be
committed or placed in the Nix store. The module creates only the root-owned
0700 parent directories. A missing token is expected to prevent the service
from registering until the operator provisions it.

Useful checks on `r640-0` after provisioning the token:

```sh
systemctl status github-runner-meta-bal.service
journalctl -u github-runner-meta-bal.service --no-pager
```

The runner is ephemeral, so successful job completion deregisters it and the
service re-registers a fresh runner instance using the PAT on its next start.
