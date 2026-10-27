# October 2026 host dependency security update

The root host nixpkgs input is updated to `3ec636362e1816bc2f0888fa0fa2c69f1bc9e504` (NAR hash `sha256-rZLrzrC6i+jnTAlvPZHogKDulY7WWDEv9hJeHieO7Zw=`). It supplies Nix 2.34.9, which includes the evaluator and daemon fixes described in the [Nix advisory](https://discourse.nixos.org/t/security-advisory-for-nix-and-lix-october-2026/80547), and the [system CA mitigation](https://github.com/NixOS/nixpkgs/issues/576485) for CVE-2026-111943.

`nix build --no-link --no-update-lock-file .#checks.x86_64-linux.host-security` checks every exported machine's selected Nix version and CA bundle. It identifies all four roots named by the upstream mitigation by SHA-256 fingerprint, accepting absence or a record with no trusted uses and explicit rejection of eight named purposes. It also verifies the old Comodo root's S/MIME trust is rejected. The check does not prove rejection for every possible OpenSSL purpose: for example, ocsphelper verification succeeds with the selected bundle. It rejects old trusted certificate fixtures and unpatched Nix versions. The version gate deliberately fails on other Nix release lines until their security status is reviewed.

This is repository evidence, not evidence that an installed host has been updated. Applications with embedded or independently managed root stores require separate investigation; updating the system bundle does not establish their coverage. OpenBao/Registry is tracked separately in [issue #41](https://github.com/pbert5/nix-arbor/issues/41).

The Registry input pins component commit `e070aadb479b6a8ab9b38a49bc05df1f9b6fcd49`, whose own nixpkgs graph selects OpenBao 2.7.2 for Registry checks. The separate root host nixpkgs still selects OpenBao 2.7.1. No enabled root OpenBao consumer was established in this review; any future root consumer must select a patched package before enablement. Installed and embedded service exposure remains unverified.

## Operator procedure after review and merge

Run these steps only after the PR is reviewed and merged, from the intended host's normal Nix Arbor checkout. They are future operator instructions; this workstream did not activate or inspect any installed host.

1. Fetch the reviewed configuration:

```sh
git fetch origin
git switch main
git pull --ff-only origin main
```

2. Select the intended flake output (`desktoptoodle`, `eVolver`, or `r640-0`), confirm its package version, and build without activation:

```sh
nix flake metadata --no-update-lock-file
nix eval --no-update-lock-file --raw .#nixosConfigurations.<host>.config.nix.package.version
nix build --no-link --no-update-lock-file .#nixosConfigurations.<host>.config.system.build.toplevel
```

3. Activate only through the normal operator procedure for that host. On `desktoptoodle` or `eVolver`, run `sudo nixos-rebuild switch --flake .#<host>` on the target (or include the configured `--target-host`). For `r640-0`, use `./tools/r640/switch --check`, then `./tools/r640/switch --dry-run`, then the normal `./tools/r640/switch` invocation only as its operator; see [the R640 switch guide](r640-switch.md).

4. After activation, verify the client, running daemon executable, and installed CA bundle:

```sh
nix --version
nix store ping
pid=$(systemctl show nix-daemon.service --property=MainPID --value)
test "$pid" -gt 1
sudo readlink -f "/proc/$pid/exe"
readlink -f /etc/ssl/certs/ca-certificates.crt
```

The client should report Nix 2.34.9, and the daemon executable path should resolve to the selected Nix 2.34.9 store package. The CA path should resolve to the activated system bundle. With OpenSSL available, run the repository guard against the installed bundle from a temporary directory:

```sh
(
  set -eu
  checkout=$(git rev-parse --show-toplevel)
  tmpdir=$(mktemp -d)
  trap 'rm -rf -- "$tmpdir"' EXIT
  cd "$tmpdir"
  bash "$checkout/modules/check-ca-bundle.sh" /etc/ssl/certs/ca-certificates.crt
)
```

If any check fails or the expected paths are absent, stop and investigate before treating the host as updated. Embedded or independently managed application stores remain separate coverage.

The development shell and the two server profiles select free RTK 0.50.0 from the existing codex-nixpkgs pin. Its Git wrapper depends on OpenSSL 3.5.8, which is also present in the existing Codex closure and predates upstream 3.5.9 security fixes. Applicability to these CLI uses has not been established; see https://openssl-library.org/news/vulnerabilities-3.5/. Review this dependency and the free-license regression when refreshing codex-nixpkgs.
