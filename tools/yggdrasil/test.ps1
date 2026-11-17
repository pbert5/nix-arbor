$ErrorActionPreference = 'Stop'
$global:Calls = @()
function yggdrasilctl { $global:Calls += ,@($args); $global:LASTEXITCODE = 0 }
function ssh { $global:Calls += ,@($args); $global:LASTEXITCODE = 0 }
$tool = Join-Path $PSScriptRoot 'arbor-ygg.ps1'
function Assert($condition, $message) { if (-not $condition) { throw $message } }
function Reject($action) {
    $rejected = $false
    try { & $action } catch { $rejected = $true }
    Assert $rejected 'Expected the command to reject invalid input'
}
& $tool identity
Assert ($global:Calls[-1][0] -eq 'getSelf') 'identity must ask the daemon for its public identity'
& $tool peers
Assert ($global:Calls[-1][0] -eq 'getPeers') 'peers must query the daemon'
$key = 'a' * 64
& $tool connect -Listener "tls://192.0.2.1:1234?key=$key"
Assert ($global:Calls[-1][1] -eq "uri=tls://192.0.2.1:1234?key=$key") 'connect must pass the pinned listener intact'
$count = $global:Calls.Count
Reject { & $tool connect -Listener 'tls://192.0.2.1:1234' }
Reject { & $tool connect -Listener "tls://192.0.2.1:1234?key=$key&key=$key" }
Reject { & $tool connect -Listener "tls://192.0.2.1:1234?key=$key&x=1" }
Reject { & $tool connect -Listener "tls://192.0.2.1:1234?KEY=$key" }
Assert ($global:Calls.Count -eq $count) 'invalid listener must not reach the daemon'
& $tool ssh -Address '200:1234::1' -User 'alice'
Assert ($global:Calls[-1][0] -eq 'alice@200:1234::1') 'ssh must receive the chosen overlay destination'
Reject { & $tool ssh -Address 'example.org' -User 'alice' }
Reject { & $tool ssh -Address '200:1234::1' -User '-bad' }
function yggdrasilctl { $global:LASTEXITCODE = 9 }
Reject { & $tool peers }
Write-Host 'Windows Yggdrasil helper checks passed'
