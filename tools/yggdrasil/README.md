# Arbor Connect for Windows and Linux

Arbor Connect runs a private Yggdrasil interface and a second, transport-only
Yggdrasil process. The private process peers with the sidecar on loopback.
Each process has its own persistent key. The sidecar connects to operator-supplied
upstreams and has no TUN, multicast discovery, or admin API. The app is an
outbound guest client. It installs a temporary inbound firewall policy before
starting the daemons.

Copy this directory to your computer or use it from a clone. The client runs
directly from Python. Keep the app in a trusted directory when running elevated.
From that directory run the examples below.

## Prerequisites

- **Linux** needs Python 3.10+, iproute2, nftables, a working TUN device,
  Yggdrasil 0.5.14 or 0.5.15, and optionally an OpenSSH client.
  Install your distribution's packages or the architecture-specific upstream
  package. For example, on Debian/Ubuntu install `python3 iproute2 nftables
  openssh-client` with apt and install the official Yggdrasil .deb.
- **Windows** needs Python 3.13+, Yggdrasil 0.5.15 with its Wintun driver,
  Windows PowerShell with NetSecurity, and optionally the Windows OpenSSH
  client feature. Use the upstream MSI for your architecture. The app also
  looks for the daemon in the default Program Files installation directory.
- Use a machine on which you can dedicate the Yggdrasil route to this client.
  Package installers may start a default service. Inspect it with
  `systemctl status yggdrasil` or `Get-Service *ygg*` and stop it before
  starting Arbor Connect if this machine should use the portable profile.
  The client leaves existing keys and service settings under your control.
- Ask the operator for an upstream peering listener URI and its verified
  public key. The upstream must be reachable directly from your laptop, and
  belong to the mesh on which the intended destination is reachable.

[Upstream installation guides](https://yggdrasil-network.github.io/installation.html)
and [official packages and SHA-256 checksums](https://github.com/yggdrasil-network/yggdrasil-go/releases/tag/v0.5.15).

## Set up and connect

Create a profile once. Replace the example address, port, and public key. Repeat
`--peer` for additional upstreams. On Linux run:

```sh
sudo python3 arbor-connect.py init --peer 'tls://192.0.2.10:14743?key=REPLACE_WITH_64_HEX_DIGITS'
sudo python3 arbor-connect.py identity
sudo python3 arbor-connect.py up
```

On Windows use an elevated PowerShell under the same Windows account:

```powershell
py -3.13 arbor-connect.py init --peer 'tls://192.0.2.10:14743?key=REPLACE_WITH_64_HEX_DIGITS'
py -3.13 arbor-connect.py identity
py -3.13 arbor-connect.py up
```

Give the operator the three public values printed by `identity`. A restricted
upstream listener admits the **sidecar public key**. Destination policies use
the **private address** to permit a guest source and specific services. Use the
**private public key** for private inventory identity. The two daemon identities
and the Arbor Registry signing identity serve different purposes.

The foreground command streams both Yggdrasil logs. Look for both the loopback
and upstream peer connections. A ready local interface alone cannot establish
that a remote service is reachable. From another terminal, replace the address
and SSH account with values verified with the operator:

```sh
sudo python3 arbor-connect.py status
python3 arbor-connect.py check 200:1234::1 --port 22
python3 arbor-connect.py ssh 200:1234::1 --user alice
```

On Windows replace `python3` with `py -3.13` and run `status` under the profile
owner. Use your normal login for SSH and verify the host key with the operator.
Press Ctrl+C in the foreground terminal or run `down` as the profile owner to
stop both daemons. To try a different upstream without rotating identities,
use `up --peer 'tls://...'`. To use a different loopback port, set `init --port`
when creating a profile.

Linux state defaults to `/var/lib/arbor-connect`. Windows uses
`%LOCALAPPDATA%\ArborConnect`. Set `--state-dir PATH` **before the command** to
use another profile under a trusted, existing parent directory. Back up
`identity.json` as a secret. A second init refuses to replace an existing profile.
The loopback link authenticates the private key at the sidecar and pins the
sidecar key at the private process. On the shared mesh, routed traffic may
originate beyond those direct peers. Linux filters unsolicited traffic on the
private interface and drops forwarding from it. Windows blocks incoming
connections from the Yggdrasil source range on all profiles and requires IPv6
forwarding disabled. This client does not publish a server.

## Arbor Registry

Use `python3 arbor-connect.py enrollment --help` for offline operator pairing
and the [enrollment guide](ENROLLMENT.md) for request, authority approval, and
verified receipt steps. Operators manage network admission and SSH authorization
separately.

## Existing Windows single-daemon helper

Install and start Yggdrasil for Windows version 0.5.15 or newer with a persistent identity, and make
`yggdrasilctl.exe` and Windows OpenSSH `ssh.exe` available on `PATH`.
If installed in the default MSI location, add the directory for this session:

```powershell
$env:Path += ";$env:ProgramFiles\Yggdrasil"
```

Use a PowerShell session with access to the running daemon's admin socket; follow
the installation's permissions. These helpers use the existing daemon and do
not create or modify its configuration or keys. Share only the public key and
IPv6 address shown by `identity`, never the private key or config file.

From the checkout root in PowerShell:

```powershell
.\tools\yggdrasil\arbor-ygg.ps1 identity
# After the operator has authorized the guest and supplied a pinned listener:
.\tools\yggdrasil\arbor-ygg.ps1 connect -Listener 'tls://192.0.2.10:12345?key=REPLACE_WITH_64_HEX_PUBLIC_KEY'
.\tools\yggdrasil\arbor-ygg.ps1 peers
.\tools\yggdrasil\arbor-ygg.ps1 ssh -Address '200:1234::1' -User 'alice'
```

Replace every example with the operator's actual values. The listener must be
reachable from Windows over LAN or Tailscale, and the `key` is the *listener's*
public key, verified with the operator. The `connect` command requires that
pin and adds a runtime peer; it does not persist across daemon restarts. If the
daemon reports the peer is already configured, check its existing pin; this
command does not replace it. Check
`peers` for a live connection before testing SSH. The SSH command uses the
actual destination host's Yggdrasil IPv6 address and normal OpenSSH host-key
verification and authentication; peering alone does not grant SSH access.

The host operator must first configure and deploy a reachable private listener,
including its transport firewall and route. The private module consumes a
`site` inventory; where it is used, the corresponding values are:

```nix
# Example site attributes, merged into the operator's existing inventory.
externalIncomingAccess.yggdrasil.byHost."listener-host".publicKeys = [
  "GUEST_PUBLIC_KEY"
];
externalIncomingAccess.yggdrasil.byHost."destination-host".sourceAddresses = [
  "GUEST_YGG_IPV6"
];
```

Add the guest public key to every listener it connects to. On each destination,
add the guest address to `sourceAddresses` when overlay peer-source filtering
is enabled; also allow TCP/22 on the overlay and configure an authorized SSH
key for the intended user. The listener and destination can be the same host,
in which case merge both attributes under that host. These are module input
attributes, not an automatic modification to the root flake; use the actual
host's inventory mechanism and review and deploy changes separately. A public
Yggdrasil peering sidecar is not a substitute for a reachable private listener.
See [networking status](../../docs/networking-status.md) for the integration
and VM validation still outstanding.

Run the helper checks with `pwsh -NoProfile -File tools/yggdrasil/test.ps1`.
They mock the external commands and do not test a live Windows network.

## Crash recovery

A normal `down` or Ctrl+C stops the children before removing the firewall rule.
If the supervisor is forcibly killed, the owned daemons or firewall rule may
survive. The profile's `session.json` records the daemon executable, PIDs and
the exact unique firewall name. Verify the supervisor is gone and confirm each
surviving daemon's executable, creation time and parent before stopping it.
PIDs can be reused. Rebooting the machine also clears orphan processes and the
temporary Linux nftables table. On Windows, remove the recorded rule from
PersistentStore after the children stop, even if you rebooted:

```powershell
Remove-NetFirewallRule -PolicyStore PersistentStore -Name 'arbor_ygg_REPLACE_WITH_RECORDED_ID'
```

On Linux, inspect `sudo nft list tables` and remove only the recorded table
with `sudo nft delete table inet arbor_ygg_REPLACE_WITH_RECORDED_ID` if it
remains. Confirm that the interface and route have gone, then delete the
profile's `session.json`. Keep `identity.json` to reuse the same keys.

## Verification

On Linux run `./test-portable-linux.sh` with Bash, unshare, iproute2, jq,
nftables, Python and Yggdrasil on PATH. It uses fresh user, mount, PID and
network namespaces, disposable keys and a temporary operator peer. It checks
real outbound TCP, denial of an incoming connection to a listening guest
service, stable identities and teardown. Unprivileged user namespaces and
`/dev/net/tun` must be available.

The Windows path needs validation on a native Windows host with Wintun and
Defender Firewall. In a disposable Windows VM, run the setup steps above,
confirm that `up` reports the private interface and logs both peer connections,
and use `check` against the operator's test service. With a temporary listener
bound on the guest, confirm a peer cannot initiate a connection, then verify
`down` removes the interface and the recorded firewall rule.
