# Guarded NixOS Anywhere Installation

`clusterctl install` is the destructive bare-metal installation boundary. It
uses the flake-pinned `nixos-anywhere` package and a Disko layout stored in
`inventory/host-bootstrap.nix`.

No current machine is installable. Existing install records remain disabled so
their connection data, hardware checks, and Disko layouts can be reviewed
without authorizing a disk rewrite.

## Safety Model

An installation proceeds only when all of these checks pass:

1. The host exists in both `inventory/hosts.nix` and
   `inventory/host-bootstrap.nix`.
2. Both inventory entries set `enable = true` and carry the same
   `installationId`.
3. SSH reaches the configured target without a command-line target override.
4. The remote hostname and `/etc/clusterctl-install-target` marker identify the
   repository's live installer, rather than an installed NixOS system.
5. DMI vendor and product values match inventory.
6. Exactly one Disko device is configured.
7. That device exists, is unmounted, and falls within the configured byte-size
   range.
8. The operator supplies `--confirm` with the exact inventory
   `installationId`.

The command omits nixos-anywhere's kexec phase. This preserves the device
mapping checked during preflight through partitioning and installation.

## Enabling A New Target

Do not enable an existing managed machine. For a genuinely new target:

1. Add its normal host record to `inventory/hosts.nix`.
2. Add all installation access, live-environment identity, hardware identity,
   disk-size bounds, and Disko data to `inventory/host-bootstrap.nix`.
3. Give both entries the same specific `installationId`.
4. Boot the repository live installer on the intended hardware.
5. Set `enable = true` in both entries only for the installation window.
6. Run the preflight:

   ```console
   clusterctl install HOST --dry-run
   ```

7. Review every reported value, then install:

   ```console
   clusterctl install HOST --confirm INSTALLATION_ID
   ```

8. Return both `enable` values to `false` immediately after installation.

`--dry-run` still connects over SSH and performs every remote safety check, but
it never invokes nixos-anywhere. Normal fleet convergence remains under
`clusterctl deploy`; it does not use this installation path.
