# Host Security Baseline

Hosts that select the `base` dendrite receive the shared security baseline from
`dendrites/base/leaves/security.nix`.

## Current Baseline

The base security leaf:

- enables the NixOS fail2ban service and its default SSH jail;
- installs `aide` and `lsof` in the system profile; and
- enables the OpenSnitch daemon by default on leader and
  `system/workstation` hosts.

OpenSnitch is explicitly configured with `DefaultAction = "allow"`,
`DefaultDuration = "once"`, and `InterceptUnknown = false`. Re-enabling the
daemon therefore observes unmatched connections without introducing a
deny-by-default policy. Any future blocking behavior must come from explicit
rules or an intentional default-action change.

AIDE is currently package-only. The flake does not yet provide an AIDE policy,
initialize its database, promote a newly initialized database, or schedule
integrity checks. Pass an explicit configuration path when operating it.

## Fail2ban Lockout Prevention

`services.fail2ban.ignoreIP` is assembled from:

- IPv4 and IPv6 loopback;
- numeric target addresses from `inventory/host-bootstrap.nix`;
- bootstrap addresses for hosts whose cluster identity role is `leader`;
- the current host's bootstrap target; and
- host-specific values from `org.security.fail2ban.trustedIPs`.

The derived list currently includes the known Tailscale bootstrap addresses for
the two leaders:

| Host | Trusted address |
|---|---|
| `desktoptoodle` | `100.64.0.10` |
| `r640-0` | `100.64.0.10` |

The iPhone Tailscale address is not recorded in inventory yet. After enrollment,
add its stable Tailscale IP to the relevant host entry:

```nix
org.security.fail2ban.trustedIPs = [
  "100.x.y.z"
];
```

Do not use the entire `100.64.0.0/10` Tailscale range unless every device in
the tailnet should bypass fail2ban.

Evaluate the effective list before deployment:

```console
nix eval .#nixosConfigurations.desktoptoodle.config.services.fail2ban.ignoreIP --json
```

## Operations

Inspect fail2ban and its SSH jail:

```console
systemctl status fail2ban
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

Inspect OpenSnitch:

```console
systemctl status opensnitchd
journalctl -u opensnitchd -b
```

Run AIDE with an operator-managed configuration:

```console
sudo aide --config /etc/aide.conf --init
sudo aide --config /etc/aide.conf --check
```

Find the process listening on a port:

```console
sudo lsof -nP -iTCP:22 -sTCP:LISTEN
```

The same commands are available through navi:

```console
navi --tag-rules security
```

The sheet is published as `base-security.cheat` from
`dendrites/base/cheats/security.cheat`.
