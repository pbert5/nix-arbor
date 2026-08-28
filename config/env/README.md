# r640 transitional environment

`env.nix` contains public, structural fallback facts only. The optional
password inputs are SOPS-encrypted age secrets, loaded from
`/etc/nix-arbor/r640-0.sops.yaml` using the host age key at
`/var/lib/host-age/keys.txt`. Enable `arbor.environment.secrets` only after
those files have been provisioned; do not commit either file or any plaintext
password/private key.

Public SSH aliases may be added to `arbor.environment.public.sshHosts` and
projected by a future user SSH module. Host keys must be verified normally.
