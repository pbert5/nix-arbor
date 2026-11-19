[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateSet('identity', 'connect', 'peers', 'ssh')]
    [string]$Action,
    [string]$Listener,
    [string]$Address,
    [string]$User
)
$ErrorActionPreference = 'Stop'

switch ($Action) {
    'identity' { & yggdrasilctl getSelf }
    'peers' { & yggdrasilctl getPeers }
    'connect' {
        # Require exactly one pinned public key; do not silently add an unpinned peer.
        if ($Listener -cnotmatch '^(tcp|tls|ws|wss|quic)://(\[[0-9a-fA-F:]+\]|[a-zA-Z0-9.-]+):([0-9]{1,5})\?key=([0-9a-fA-F]{64})$' -or
            [int]$Matches[3] -lt 1 -or [int]$Matches[3] -gt 65535) {
            throw 'Listener must be a transport URI with a port and exactly one 64-hex-digit ?key= pin.'
        }
        & yggdrasilctl addPeer "uri=$Listener"
    }
    'ssh' {
        $ip = $null
        if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$ip) -or
            $ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetworkV6 -or
            $ip.GetAddressBytes()[0] -notin 2, 3) {
            throw 'Address must be a Yggdrasil IPv6 address in 200::/7.'
        }
        if ($User -notmatch '^[a-zA-Z_][a-zA-Z0-9_.-]*$') { throw 'Provide a valid SSH user name.' }
        & ssh "$User@$Address"
    }
}
if ($LASTEXITCODE -ne 0) { throw "External command failed with exit code $LASTEXITCODE." }
