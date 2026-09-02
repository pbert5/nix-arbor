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
uses `IdentitiesOnly yes`, `IdentityAgent $SSH_AUTH_SOCK`, and one exact path
under `/home/ash/.ssh/`; wildcard paths and embedded private key material are
rejected by host assertions. The agent service does not provision or load
identities. An operator or the runtime identity owner must make the matching
private key available and load it with `ssh-add`.

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

This should show the intended `hostname`, `user`, `identityfile`, and
`identitiesonly`. Do not disable host-key verification. To add an alias,
first establish its stable endpoint and target-side public-key grant, then add
one catalog entry with an explicit identity where needed and add the matching
runtime provisioning record. Registry endpoint metadata may replace the
transitional static addresses later; it must not silently broaden grants.
