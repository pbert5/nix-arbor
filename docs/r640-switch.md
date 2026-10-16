# R640 NixOS switch operator

`./tools/r640/switch` activates only the `r640-0` output from this exact
checkout. The script is intended for an operator on host `r640-0`; the Codex
implementation workflow must not invoke a full activation.

Before any mode continues, the script requires the canonical primary checkout
at `/home/ash/documents/nix-arbor`, branch `main`, a clean worktree, the matching
NixOS hostname, the expected flake output, mounted `/mypool`, the imported
`mypool` ZFS pool, and the existing Docker/build directories.

```sh
./tools/r640/switch --check
./tools/r640/switch --dry-run
./tools/r640/switch
```

`--check` runs preflight only. `--dry-run` builds the exact system closure but
does not prompt for sudo or activate it. A normal invocation prompts with
`sudo -v`, records the active, booted, and profile system paths plus the
available system generations and rollback command under
`/var/lib/nix-arbor-r640-switch/`, then runs:

```sh
sudo nixos-rebuild switch --flake /home/ash/documents/nix-arbor#r640-0
```

After activation, it reports the installed `codex --version`. To roll back,
use the exact command printed by the script, normally:

```sh
sudo nixos-rebuild switch --rollback --flake /home/ash/documents/nix-arbor#r640-0
```

The flake pins a separate Nixpkgs revision for Codex only, so this refresh does
not update unrelated host package inputs. Do not run `nix flake update` as part
of this operator step.
