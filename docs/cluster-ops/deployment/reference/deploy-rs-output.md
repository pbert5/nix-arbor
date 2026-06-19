# Reading `deploy-rs` Output

This guide explains the important parts of the `deploy-rs` output you pasted.

## Example Profile Block

```text
[r640-0.system]
user = "root"
ssh_user = "root"
hostname = "200:db8::10"
```

What each field means:

- `r640-0.system`
  the node and profile name
- `user = "root"`
  the target-side activation user
- `ssh_user = "root"`
  the SSH login user
- `hostname = "202:…"`
  the transport address chosen by the generated deploy surface

## Why This Was A Good Sign

When `hostname` changed from the bootstrap IP to the Ygg IPv6, it showed that:

- the host had an enrolled Ygg address
- `deploymentTransport` had switched to `privateYggdrasil`
- the generated deploy surface was now preferring the overlay

## Activation Success Lines

These lines mean the deployment completed successfully:

- `Activation succeeded!`
- `Found canary file, done waiting!`
- `Deployment confirmed.`

That means:

- the copied profile activated
- magic rollback did not trigger
- the host stayed reachable long enough to confirm the deployment
