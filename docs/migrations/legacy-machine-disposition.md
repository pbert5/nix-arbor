# Legacy machine disposition

This record covers the legacy hosts found in the inspected Flake Devbox
reference at commit `4ac3560d5ffcf414b210918f45d18f54f5513fa1`. The descriptors
under `config/legacy-machines/` are deliberately suspended and data-only: they retain
stable identity and a small hardware snapshot for inventory and future
explicit recovery, but they do not activate legacy services or configuration.
For migrated physical machines, they are provenance records alongside—not instead
of—the active definitions under `config/machines/`.

| Host | Evidence inspected | Disposition | Deferred scope |
|---|---|---|---|
| `canoodle` | `config/hosts.json`, `src/hosts/canoodle/canoodle.nix`, generated hardware module | Migrated machine | `config/machines/canoodle/` supplies known EFI/ext4 hardware, hardened public SSH access, the shared Arbor desktop baseline, and the participant runtime; legacy desktop/NVIDIA workload parity remains deferred |
| `eVolver` | `config/hosts.json`, `src/hosts/eVolver/eVolver.nix`, generated hardware module and facter report | Migrated machine | `config/machines/eVolver/` supplies known EFI/ext4 hardware, hardened public SSH access, the shared Arbor desktop baseline, and the participant runtime; legacy workstation/network workload parity remains deferred |
| `t320-0` | `config/hosts.json`, `src/hosts/t320-0/t320-0.nix`, generated hardware module | Migrated machine | `config/machines/t320-0/` now supplies EFI boot, labeled root filesystems, LAN bridge, public SSH access, and the Arbor participant runtime; ZFS, tape, and media workloads remain deferred |
| `dev-machine` | `src/hosts/dev-machine/dev-machine.nix` | Template-only | Generic users, links, boot, and game service are intentionally not ported |

The suspended legacy records remain provenance only. The migrated machine
definitions use the public shared SSH access ledger; no credentials, private
keys, runtime endpoints, or legacy application state are copied from Flake
Devbox. `dev-machine` remains template/profile-only because the reference did
not establish it as a stable physical machine. Deferred services still require
explicit profile selection and review.
