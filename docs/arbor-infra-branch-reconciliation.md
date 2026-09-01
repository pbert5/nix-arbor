# Arbor infrastructure branch reconciliation

This manifest records the branch dispositions used for the 2026-09
normalization. Component implementation is owned by the standalone repos;
the root repo carries composition and pins.

| old ref | old tip | disposition | canonical replacement | archive/preservation |
| --- | --- | --- | --- | --- |
| `codex/arbor-operator-migration` | `d942d857be7c1b4b141f4ccd296b2c50dc47462a` | root integration split and carried forward | `nix-arbor:arbor-infra-dev` | `archive/arbor-operator-migration-final` |
| `agent/luna/self-root-identity-cli-hardened` | `5c919da25abeb228ad0c31bbf7291143fa4b5225` | Manager implementation carried forward | `arbor-manager:arbor-infra-dev` | retained by canonical history |
| `agent/manager/standalone-finalize` | `3d46770a99bfad5fdffe9f9076203ebc2fc70a69` | Manager receipt security carried forward | `arbor-manager:arbor-infra-dev` | retained by canonical history |
| `integration/nix-arbor-operator-migration` | `4eb20b5f41a5a39fe3d428129aeb80a0b5dd60a8` | runtime-doctor behavior superseded by the bounded canonical doctor | `arbor-manager:arbor-infra-dev` | old branch retained for provenance |
| `agent/luna/self-root-graph-vm-final-v2` | `a0d85c0c2ac842b59ffe0c705ba132b6bd3f2e58` | Registry graph harness carried forward | `arbor-registry:arbor-infra-dev` | retained by canonical history |
| `agent/luna/recovery-security-v5` | `9f3d689f54052aabdf9510742381b063683d0a6d` | Registry recovery hardening carried forward | `arbor-registry:arbor-infra-dev` | retained by canonical history |
| unresolved `agent/*` and dirty worktrees | varied | preserved pending owner/review | none | active WIP remains in place |

The Registry canonical tip is `7a07be55ea31898aceb77da229bb119a1ca26c29`.
Its graph acceptance work is present but not claimed green without a runtime
acceptance run. The root main line remains stable and pins component main.
