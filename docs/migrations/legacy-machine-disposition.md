# Legacy machine disposition

This record covers the legacy hosts found in the inspected Flake Devbox
reference at commit `4ac3560d5ffcf414b210918f45d18f54f5513fa1`. The descriptors
under `config/machines/` are deliberately suspended and data-only: they retain
stable identity and a small hardware snapshot for inventory and future
explicit recovery, but they do not activate legacy services or configuration.

| Host | Evidence inspected | Disposition | Deferred scope |
|---|---|---|---|
| `canoodle` | `config/hosts.json`, `src/hosts/canoodle/canoodle.nix`, generated hardware module | Identity-only | Desktop/NVIDIA and cluster services require a new host-parity review |
| `eVolver` | `config/hosts.json`, `src/hosts/eVolver/eVolver.nix`, generated hardware module and facter report | Identity-only | Workstation and network services remain unmanaged |
| `t320-0` | `config/hosts.json`, `src/hosts/t320-0/t320-0.nix`, generated hardware module | Identity-only | ZFS, tape, media, and network bridge require a separate component review |
| `dev-machine` | `src/hosts/dev-machine/dev-machine.nix` | Template-only | Generic users, links, boot, and game service are intentionally not ported |

No SSH keys, credentials, runtime endpoints, generated modules, service
definitions, or user-specific application state are part of these records.
Reactivation requires an explicit profile and reviewed local hardware module.
