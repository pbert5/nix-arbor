set shell := ["bash", "-euo", "pipefail", "-c"]

public_submodules := "packages/AshZsh references/flake-devbox packages/AshesTools packages/AshDesktopApps packages/tiling-desktop"

help:
    @printf '%s\n' 'Use native Nix commands: nix develop, nix flake check, nix fmt, navi'

agents:
    @./scripts/agent-worktree list

wt-new task agent='{{env_var("NIX_ARBOR_AGENT", "agent")}}':
    ./scripts/agent-worktree new {{quote(task)}} {{quote(agent)}}

wt-list:
    ./scripts/agent-worktree list

wt-status:
    ./scripts/agent-worktree status

wt-status-task task:
    ./scripts/agent-worktree status {{quote(task)}}

wt-remove task force='':
    ./scripts/agent-worktree remove {{quote(task)}} {{quote(force)}}

wt-clean force='':
    ./scripts/agent-worktree cleanup-merged {{quote(force)}}

wt-prune:
    ./scripts/agent-worktree prune

submodules:
    git submodule update --init -- {{public_submodules}}

check:
    nix flake check

fmt:
    nix fmt

lint:
    statix check modules
    deadnix --fail flake.nix modules

show:
    nix flake show

metadata:
    nix flake metadata

shell:
    nix develop

repl:
    nix repl
