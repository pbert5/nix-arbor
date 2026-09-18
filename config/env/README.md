# r640 transitional environment

`env.nix` contains public, structural fallback facts only. Operator-provided
files are represented by `arbor.environment.externalFiles`: entries contain an
absolute runtime `path`, an expected `owner`, `group`, `mode`, and optional
`neededForUsers` metadata. The interface contains no file contents and does
not select a provider. For example, an SSH host may use a private key without
embedding it in Nix:

```nix
arbor.environment.public.sshHosts.desktoptoodle.identityFile = [
  config.arbor.environment.externalFiles.files.desktoptoodleSshIdentity.path
];
```

The existing optional SOPS provider maps the r640 password-hash entries to
their declared paths. Enable `arbor.environment.secrets` only after the
encrypted file at the declared path and its host age key have been provisioned;
do not commit either file or any plaintext password/private key. The default
secret mode is `0400` and the default owner/group is `root`/`root`.

Public SSH aliases may be added to `arbor.environment.public.sshHosts` and
projected by a future user SSH module. Host keys must be verified normally.
