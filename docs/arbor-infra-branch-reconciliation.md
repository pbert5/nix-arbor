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

## WS1 root reconciliation disposition

The approved two-parent merge used fresh `main@9c5f2b4f37db7b9d336e70db498e3d272eba1314`,
`arbor-infra-dev@3f1349c138cb0cc91abfc419112cd35965be12ef`, and merge base
`ae1f29cc82f3ea6fe93f02769930e6c5cd08c6c3`. The merge checkpoint is
`9239a61cd34db8538eb06f1ab898b5d883236f86`.

| dev-only commit | disposition |
| --- | --- |
| `3776277e601ef09c61d94d8b352e00d643ac3bc1` | Carried: Manager/Registry development input refs and exact approved lock revisions. |
| `b96e647cf5838bd72d7695dc1d8a5889796a5c50` | Carried: Manager/Registry submodule branch metadata is `arbor-infra-dev`. |
| `17f6bd50ec417957d78b410ff66dcf8c185e8de9` | Carried selectively: Arbor composition, operator/participant profiles, external-file/SOPS interfaces, tests, and static machine facts; main access/host/workflow behavior remains authoritative and real descriptors are not opted into Arbor participation. |
| `f3a353313f308d9a950abfe3116bd5fcda40e310` | Carried as reconciliation provenance; stale branch claims were refreshed for WS1. |
| `eae3c8770a0bae5571b4c84ba53854ab0a6e1049` | Carried as valid supersession/provenance documentation. |
| `b1195a4b2020dad1d78ca073f6134d7418915aea` | Superseded by current-main `fb1126b64aafd9fd2b22c2418ffd3323057666b7`; stable patch IDs match, so main worktree wording/behavior is retained. |
| `0af54e47077fdf1e6890db45d1f02960dbd061a5` | Superseded by current-main `f7294b299058cdf096a5dabc278f4afd8a2233f6`; range evidence shows the same convention with current-main ignore/worktree behavior authoritative. |
| `92eefd1359d9faaeca73a8033ca59d456bb19786` | Superseded by current-main `3aaf30f2d15b4c0908c02662a92b9386a2cd7f73` and later main hardening; stable patch IDs match and main r640 storage is retained. |
| `aa8493925bcc12611fca0ae24c9036e7c13eca86` | Carried as current-state documentation, then refreshed with WS1 provenance and downstream freeze state. |
| `3f1349c138cb0cc91abfc419112cd35965be12ef` | Carried as README discoverability, then merged into the preserved long main README with operator/current-state links. |

The clean-merge audit also restored main-authoritative effective SSH grants,
Codex/worktree behavior, README breadth, and r640 storage hardening. No live
host, Registry, OpenBao, network, secret, or physical state was mutated.
