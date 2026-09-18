# Physical access-matrix verification

This is a redacted operator runbook for the bootstrap SSH paths preserved by
the Arbor migration. The bounded observations below were performed on
2026-08-31; pending entries are intentionally not inferred from transport
reachability.

## Public identities

- `laptopOperatorKeys`: the supplied `admin@toptoodle` Ed25519 key and the
  supplied `phsilbert@gmail.com` Ed25519 key.
- `recoveryOperatorKeys`: the existing recovery/operator keys retained by the
  repository.
- `desktoptoodleDeploymentKeys`: the existing desktoptoodle cluster-leader
  public key.
- `r640DeploymentKeys`: the recovered `r640-0` public deployment key. The
  corresponding private key is not in Git, Nix source, or the Nix store.
- `r640EvolverDeployer`: a newly generated runtime-only Ed25519 identity on
  r640, fingerprint `SHA256:78Qwb3eauvwxVczH8W1vJ17Vs74bgEME8fgO+vYeA/E`.
  Only its public half was authorized on eVolver; the private half is not
  recorded here.

Only public keys and their labels belong in this repository. Do not copy a
private SSH key into the repository, a Nix expression, command arguments, or
logs.

## Verification procedure

From each source, use the intended runtime identity with bounded, non-
interactive SSH. Record only the source label, target, remote account,
hostname, successful key fingerprint, and whether the route was bootstrap or
Arbor/private-Ygg. Never record private-key paths or contents in shared logs.

```sh
ssh -o BatchMode=yes -o IdentitiesOnly=yes \
  -o ConnectTimeout=10 \
  -i "$IDENTITY" "$ACCOUNT@$TARGET" 'hostname'
```

Repeat before activation, after each activation, and after private-Ygg
convergence. Confirm the remote account and hostname rather than treating a
TCP connection as authentication proof.

| Path | Bootstrap SSH | Arbor route | Private Ygg | Verified |
| --- | --- | --- | --- | --- |
| Laptop -> r640-0 | pending operator check | pending | pending | no |
| Laptop -> desktoptoodle | pending operator check | pending | pending | no |
| Laptop -> eVolver | PASS (root; deploy_rsa) | pending | pending | pre-convergence |
| desktoptoodle -> r640-0 | pending operator check | pending | pending | no |
| desktoptoodle -> eVolver | pending operator check | pending | pending | no |
| r640-0 -> eVolver | PASS (root; dedicated runtime identity) | pending | pending | pre-convergence |

The r640-0 -> eVolver check passed with the dedicated runtime identity listed
above. The identity was generated on r640 and is not a Nix or Git input. The
older r640 cluster-leader key was not accepted as Arbor deployment evidence.

r640 itself remains blocked for activation: `ash@192.168.86.40` is reachable,
but `sudo -n` reports that a password is required and root SSH is denied.
No password was placed in automation and no broad sudo rule was installed.

## Failure and recovery checks

For each applicable path, distinguish DNS/route failure from public-key
authentication failure. Keep at least one physical bootstrap route available
while testing private-Ygg, Registry, provider, restart, and reboot recovery.

After private-Ygg convergence, record the route selected by `arbor-manager
route ...` and compare it with an actual SSH connection. A discovered Ygg node
is transport only; Registry enrollment and accepted state remain the trust
authority.
