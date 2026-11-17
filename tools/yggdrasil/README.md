# Windows guest on the private Yggdrasil network

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
