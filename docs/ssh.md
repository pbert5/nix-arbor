# Arbor SSH operator guide

Arbor's transitional public SSH host catalog lives in
`config/env.nix`, under `arbor.environment.public.sshHosts`. Home Manager
projects that catalog into Ash's and Madeline's SSH configuration on managed
hosts. Ash also receives Home Manager's native `ssh-agent` user service on
`r640-0` and `desktoptoodle`; shell/session initialization exports
`SSH_AUTH_SOCK` for that service. The catalog contains routing facts, remote
users, and explicit identity-file paths; it does not contain private key
contents.

Public keys accepted by managed machines live in `config/access/default.nix`.
A machine opts into named public grants through
`arbor.access.authorizedKeySets`, or uses a narrowly scoped explicit grant
when the target account is outside the shared user module. eVolver explicitly
authorizes the r640 machine key for both `ash` and `root`; desktoptoodle
authorizes it for `ash`.

These are three separate pieces:

* the destination's `authorized_keys` contains a public key;
* the source user's runtime environment supplies the matching private identity;
* the SSH `Host` alias selects the endpoint, user, and identity.

The five aliases in the current matrix are an explicit allowlist. Every entry
uses `IdentitiesOnly yes`, `IdentityAgent $SSH_AUTH_SOCK`,
`AddKeysToAgent no`, `ForwardAgent no`, and one exact path from the checked-in
allowlist under `/home/ash/.ssh/`; host assertions reject any other path. The
agent service does not provision or load identities. Its private runtime
directory is managed by systemd; before each start, only the configured socket
pathname is removed so a stale socket from a dead agent cannot prevent a
restart. Explicitly loaded keys expire after eight hours, and the lingering
user service is restarted every twelve hours. An operator or the runtime
identity owner must make the matching private key available and load it with
`ssh-add`.

The current source-side private identity paths are:

* `/home/ash/.ssh/deploy_rsa` for the operator/deployment identity;
* `/home/ash/.ssh/r640-0` for the dedicated r640 machine identity;
* `/home/ash/.ssh/cluster-leader-ed25519` for the desktoptoodle leader identity;
* `/home/ash/.ssh/bal-lab-glbrc-ed25519` for BAL Lab.

The first path is present on the current operator workstation. The other
paths must be provisioned by the runtime identity/secrets owner with owner-only
permissions; none is generated or committed by this repository. In
particular, BAL Lab remains the historical manually enrolled
`bal-lab-glbrc-org-access` identity from Flake Devbox.

Inspect effective routing and identity selection with:

```sh
ssh -G <alias>
```

For a bounded local diagnostic (it never connects), run:

```sh
arbor-ssh-diagnose <alias>
```

It reports the session socket, agent listing, and selected public
configuration fields. It does not print key contents or provision credentials.

This should show the intended `hostname`, `user`, `identityfile`,
`identitiesonly`, `addkeystoagent no`, and `forwardagent false`. Do not disable
host-key verification. No stable host fingerprints are currently recorded in
the declarative catalog, so Arbor retains OpenSSH's default known-hosts
verification rather than inventing fingerprints. Recording verified
fingerprints remains security debt for a future operator-led enrollment.
To add an alias,
first establish its stable endpoint and target-side public-key grant, then add
one catalog entry with an explicit identity where needed and add the matching
runtime provisioning record. Registry endpoint metadata may replace the
transitional static addresses later; it must not silently broaden grants.

## Mosh on r640-0

Mosh is available on `r640-0` for mobile clients such as Termius. Use SSH to
bootstrap and authenticate as `ash`, for example
`ash@<r640-0 Tailscale address>`; Mosh traffic then uses UDP ports `60000-61000`
on `tailscale0` only. Keep `tmux` available above Mosh when processes or shell
work should persist independently of the client connection.
