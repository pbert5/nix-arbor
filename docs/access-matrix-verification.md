# Physical access-matrix verification

This is a redacted operator runbook for the bootstrap SSH paths preserved by
the Arbor migration. It records configuration intent only; no physical SSH
verification was performed from the repository worker environment.

## Public identities

- `laptopOperatorKeys`: the supplied `admin@toptoodle` Ed25519 key and the
  supplied `phsilbert@gmail.com` Ed25519 key.
- `recoveryOperatorKeys`: the existing recovery/operator keys retained by the
  repository.
- `desktoptoodleDeploymentKeys`: the existing desktoptoodle cluster-leader
  public key.
- `r640DeploymentKeys`: the recovered `r640-0` public deployment key. The
  corresponding private key is not in Git, Nix source, or the Nix store.

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
| Laptop -> eVolver | pending operator check | pending | pending | no |
| desktoptoodle -> r640-0 | pending operator check | pending | pending | no |
| desktoptoodle -> eVolver | pending operator check | pending | pending | no |
| r640-0 -> eVolver | pending runtime-identity check | pending | pending | no |

The r640-0 -> eVolver check must use the existing managed deployment identity
if it is provisioned through the runtime secret boundary. If it is absent,
stop and provision it through that boundary before testing; do not invent a
replacement identity in Nix.

## Failure and recovery checks

For each applicable path, distinguish DNS/route failure from public-key
authentication failure. Keep at least one physical bootstrap route available
while testing private-Ygg, Registry, provider, restart, and reboot recovery.

After private-Ygg convergence, record the route selected by `arbor-manager
route ...` and compare it with an actual SSH connection. A discovered Ygg node
is transport only; Registry enrollment and accepted state remain the trust
authority.
