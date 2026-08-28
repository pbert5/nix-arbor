# desktoptoodle parity boundary

The desktoptoodle machine imports the existing environment, SOPS, and user
abstractions. This preserves Ash's fixed identity, zsh shell, group access,
and public authorized-key recovery path without embedding private material.

NetworkManager, the Tailscale client, SSH with password authentication
disabled, Docker for development, and the existing desktop/session modules are
enabled. The checked-in configuration does not enroll Tailscale, provision an
SSH private key, or select storage/workloads.

Those runtime steps remain operator work: Tailscale needs enrollment on the
target host, and the external SSH identity path is usable only after its
private key has been provisioned. No secret values or activation workflow are
part of this parity slice.
