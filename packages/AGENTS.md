# Packages

`packages/` is for independently versioned child flakes checked out for active
development. Keep child changes in that repository's own branch/worktree;
update Nix Arbor only for an intentional submodule pointer or input change.
Initialize nested submodules with `git submodule update --init --recursive`.

`packages/arbor-manager` and `packages/arbor-registry` are standalone Git
repositories and real submodules, not parent-repository source trees. Mutating
either component requires its own branch/worktree in the child repository.
Nix Arbor `main` pins each component's `main`; `arbor-infra-dev` pins each
component's `arbor-infra-dev`. Normal builds use the remote flake inputs.
Initialized submodules are for local development through `--override-input`.
