# r640 transitional environment

`env.nix` contains public, structural fallback facts and provider-independent
runtime file references only. It never imports `.env` files and never carries
file contents into Nix evaluation. Entries contain an absolute runtime `path`,
expected `owner`, `group`, `mode`, and optional `neededForUsers` metadata.

Desktoptoodle explicitly selects the `external-files` account secret provider:

```nix
arbor.environment.secrets = {
  enable = true;
  provider = "external-files";
};
```

That mode expects the operator to provision `/run/secrets/ash-password` and
`/run/secrets/madeline-password`; Nix passes paths to account declarations and
does not require SOPS ciphertext. The existing r640 mode remains
`provider = "sops"`, using the declared encrypted file and host age key.
Never commit either provider's files or any plaintext password/private key.

The r640 SSH identity reference is `/home/ash/.ssh/cluster-leader-ed25519`,
owned by `ash:users` with owner-only mode; the obsolete `/root/.ssh/r640-0`
path is not part of the configuration.

Public SSH aliases may be added to `arbor.environment.public.sshHosts` and
projected by a future user SSH module. Host keys must be verified normally.
