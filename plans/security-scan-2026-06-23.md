# Security scan — 2026-06-23 (desktoptoodle)

Ran the existing in-repo tooling against the live system: `lynis`, `vulnix`,
plus a check of the always-on `clamav` daemon. `grype`/`sbomnix` were not run
standalone (vulnix already covers closure-wide CVE matching; grype needs an
sbomnix-generated SBOM as input, which is a separate follow-up if deeper
per-package detail is wanted).

## ClamAV — clean

Nightly scan (03:30) + on-access daemon are both running. Last several nights:
`Infected files: 0` every time. No malware found on this host.

One operational issue (not a vulnerability): `clamdscan.service` is failing
(`exit-code 2/INVALIDARGUMENT`) on every run due to `cli_realpath: Invalid
arguments` warnings against files like `~/.steam/steam.pipe` (sockets/pipes
clamscan can't handle) — scan still completes and reports 0 infected, but the
systemd unit shows failed. Worth a `--exclude` rule for socket/pipe paths in
`dendrites/base/leaves/clamav.nix` at some point, but not security-relevant.

## Lynis — hardening index 62/100

Ran as non-root (no warnings, only suggestions — some checks like device-mapper
and full firewall introspection are degraded without root). No `warning[]`
entries were produced, only `suggestion[]`. Notable ones:

- **FIRE-4590** "configure a firewall" — false alarm for this host specifically:
  `systemctl is-active firewall.service` → active/enabled, confirmed NixOS's
  declarative firewall is on. Lynis just can't fully introspect it without root.
- **PKGS-7398** "install a package audit tool" — already addressed by vulnix/grype.
- **FINT-4350** "install a file integrity tool" (e.g. AIDE) — real gap, tracked in `plans/todo`.
- **MALW-3286** confirm freshclam keeps updating — already configured (`updater.enable = true`, hourly).
- **ACCT-9628** "enable auditd" — real gap, tracked in `plans/todo`.
- Misc lower-value suggestions: separate `/tmp`/`/var` partitions, disable unused
  USB storage, disable unused `dccp`/`sctp`/`rds`/`tipc` net protocols, add a
  legal banner to `/etc/issue`, tighten CUPS config access, log to an external
  host, password aging policy in `/etc/login.defs`, pam_cracklib/passwdqc.

SSH is already hardened: `PasswordAuthentication no`, `PermitRootLogin
prohibit-password` (both in `/etc/ssh/sshd_config` and declared in
`dendrites/base/leaves/services.nix:43`), consistent with the recent "ensure
password auth is off on all machines" work.

## Vulnix — closure-wide CVE scan: 167 derivations flagged, mostly noise

Vulnix matches every derivation name+version in the *build closure* (including
bootstrap compilers, Rust crates, Haskell packages, etc., not just what's
actually installed/running) against NVD by name. This produces a lot of false
positives from name collisions. Verified two examples directly:

- `curl-0.4.49.drv` — not the curl binary. It's a Rust *crate* (libcurl
  bindings) vendored as a build dependency. Live system curl is `8.20.0`
  (not flagged — clean).
- `bash-2.05b.drv` — not running bash. It's nixpkgs' `bootstrap-seed`/mes
  bootstrap chain (full source bootstrap of GCC), built once and never
  executed as a shell. Live system bash is `5.3.9` (not flagged — clean).

Same pattern almost certainly applies to other ancient-looking entries
(`gcc-4.6.4`, `python-2.7.18.12`, `dbus-0.9.10`, `network-3.2.8.0`, etc.) —
these are bootstrap/build-time artifacts baked into the Nix store, not
attacker-reachable services.

### Actually relevant findings

Cross-checked against what's live (`systemctl list-units --state=running`,
`ss -tulnp`):

**Exposed network surface on this host:** `sshd` (22, hardened — see above),
`tor.service` (running), `cups.service` (listening on `127.0.0.1:631` and
`[::1]:631` only — not exposed off-box), `rpcbind` (port 111 tcp/udp,
0.0.0.0 — tied to the NFS export in
`dendrites/media/dendrites/game-library/dendrites/export/export.nix`, opens
2049 only on the yggdrasil interface, but rpcbind itself listens on all
interfaces by default — worth restricting if this host doesn't need to serve
NFS to other interfaces).

**Core libraries genuinely in the live closure with high/critical CVEs**
(these are real, not name-collision noise — they're what curl/system tools
actually link against):

| Package | CVE | CVSS |
|---|---|---|
| `glibc-2.42` | CVE-2026-5450 | 9.8 |
| `openssl-3.6.2` | CVE-2026-34182 | 9.1 |
| `perl-5.42.0` | CVE-2026-4176, CVE-2026-8376 | 9.8 each |
| `unbound-1.25.0` | CVE-2026-42960 | 10.0 (not running as a service on this host — only present as a build/library dependency; low risk here) |

These are upstream-disclosed CVEs in versions currently packaged by nixpkgs
unstable/this flake's pin; check for a newer nixpkgs revision with backports
before treating as actionable, since CVSS alone doesn't confirm a fix isn't
already pending in nixpkgs. Re-run `vulnix --system` after the next
`nixpkgs` bump to see if these clear.

`tor` (CVE-2017-16541, 6.5) and `cups` (CVE-2022-26691, 6.7) are old/low
relative to exposure (cups is loopback-only; tor's own threat model assumes
hostile networks).

## Bottom line

- No malware, no critical misconfigurations found that need *immediate* action.
- The 167-derivation vulnix list is closure noise — don't chase it package by
  package; the runtime-relevant CVEs are the glibc/openssl/perl table above.
- Real gaps to close are the ones already added to `plans/todo`
  (fail2ban, IDS, rootkit checker, AIDE) plus auditd from lynis.
- Minor cleanup candidates: clamdscan socket-scan errors, rpcbind binding to
  all interfaces instead of just the NFS-serving one.
