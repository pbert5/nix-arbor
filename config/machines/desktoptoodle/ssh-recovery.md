# desktoptoodle SSH recovery

This machine's declared Arbor SSH policy is key-only: `PasswordAuthentication`
and `KbdInteractiveAuthentication` are disabled, and
`PermitRootLogin = "prohibit-password"`. The effective authorized-key search
paths are the user's `~/.ssh/authorized_keys` and
`/etc/ssh/authorized_keys.d/%u`.

## Declared access

The `desktoptoodle` profile explicitly grants the r640 machine public key to
`ash` (`r640EvolverDeployer`). It does not grant a key to `root`. The source
private key is runtime-only at `/home/ash/.ssh/r640-0`; it is not generated or
stored by Arbor. The normal source-side alias is `desktoptoodle`, which targets
`ash` and uses that identity through Ash's SSH agent.

The root alias in `config/env.nix` targets `root@eVolver`, not
`root@desktoptoodle`. eVolver separately declares the r640 machine public key
for both `ash` and `root`.

## Live-state warning

On the read-only inspection of the host named `desktoptoodle`,
`/etc/ssh/authorized_keys.d/ash` contained 12 public keys and
`/etc/ssh/authorized_keys.d/root` contained six public keys. The files were
root-owned and mode `0444`; only key types, counts, comments, and fingerprints
were inspected. This does not match the checked-out desktoptoodle evaluation
(Ash: one key; root: zero keys).

Therefore the live root keys are not evidence of a durable Arbor grant. A
future activation of this checkout may remove them as part of normal
declarative reconciliation. Do not activate a desktoptoodle generation until
the operator has confirmed a physical-console or other out-of-band recovery
path and decided whether root SSH recovery is intended.

## Safe recovery checks

Run these read-only checks from console or an already-working session before
any switch:

```sh
hostnamectl --static
systemctl is-active sshd
sshd -T -f /etc/ssh/sshd_config  # requires readable host keys
stat -c '%U:%G %a %n' /etc/ssh/authorized_keys.d/ash /etc/ssh/authorized_keys.d/root
```

Do not copy private keys into the repository or Nix store, and do not replace
the shared access module to repair this machine. If root recovery is required,
make the narrowly scoped machine decision first, then update its machine
configuration and test from console before switching.
