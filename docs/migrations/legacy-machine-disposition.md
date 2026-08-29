# Legacy machine disposition

This record covers the legacy hosts found in the inspected Flake Devbox
reference at commit `4ac3560d5ffcf414b210918f45d18f54f5513fa1`. The descriptors
under `config/legacy-machines/` are deliberately suspended and data-only: they retain
stable identity and a small hardware snapshot for inventory and future
explicit recovery, but they do not activate legacy services or configuration.

| Host | Evidence inspected | Disposition | Deferred scope |
|---|---|---|---|
| `canoodle` | `config/hosts.json`, `src/hosts/canoodle/canoodle.nix`, generated hardware module | Identity-only | Desktop/NVIDIA and cluster services require a new host-parity review |
| `eVolver` | `config/hosts.json`, `src/hosts/eVolver/eVolver.nix`, generated hardware module and facter report | Identity-only | Workstation and network services remain unmanaged |
| `t320-0` | `config/hosts.json`, `src/hosts/t320-0/t320-0.nix`, generated hardware module | Migrated machine | `config/machines/t320-0/` now supplies EFI boot, labeled root filesystems, LAN bridge, public SSH access, and the Arbor participant runtime; ZFS, tape, and media workloads remain deferred |
| `dev-machine` | `src/hosts/dev-machine/dev-machine.nix` | Template-only | Generic users, links, boot, and game service are intentionally not ported |

The suspended legacy records remain provenance only. The migrated machine
definition uses the public shared SSH access ledger; no credentials, private
keys, runtime endpoints, or legacy application state are copied from Flake
Devbox. Deferred services still require explicit profile selection and review.
