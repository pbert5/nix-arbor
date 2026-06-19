# Private Overlay Bootstrap

## Identity Bootstrap Workflow

The flake now ships a bootstrap helper:

```bash
nix run .#yggdrasil-bootstrap -- --host r640-0 --target 100.64.0.10
```

There is also an alias that matches the operator workflow name more closely:

```bash
nix run .#bootstrap-host -- --host r640-0 --target 100.64.0.10
```

For first-contact machines, the flake also now ships a dedicated SSH-enabled
live installer image:

```bash
nix run .#live-installer
```

and a direct USB-writing endpoint:

```bash
nix run .#live-installer-usb -- --device /dev/sdX
```

That live image trusts the leader deployer public keys from
[`inventory/keys/leaders/`](/work/flake/inventory/keys/leaders), so a
trusted leader can root-SSH into the live environment immediately after the
target boots.

What it does:

- connects over SSH, using `root` by default
- ensures `/var/lib/yggdrasil/keys.json` exists on the target
- derives the target host's Ygg public key and Ygg address
- rewrites
  [`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
  in a canonical format with the updated public metadata
- updates
  [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
  with bootstrap target, SSH user, deployment transport, deployment tags, and
  operator-capable metadata
- can optionally create a Git commit and trigger a first deployment using the
  flake-pinned `deploy-rs` or `colmena` apps

What it does not do:

- it does not automatically rewrite `inventory/hosts.nix`
- it does not force peer-source filtering on by itself
- it does not silently redeploy peers unless you ask for that explicitly

That separation is deliberate. Enrollment updates public metadata. Rebuilds and
policy changes stay explicit.

### Normal Fleet Deployment After Enrollment

The intended two-layer workflow is now:

1. use `bootstrap-host` or `yggdrasil-bootstrap` to enroll or refresh the host
   identity over the bootstrap endpoint
2. set `deploymentTransport = "privateYggdrasil"` for hosts that should now be
   managed over Ygg
3. redeploy the enrolled host, then redeploy peers that should trust the new
   identity
4. use the flake-pinned `deploy-rs` and `colmena` apps for ordinary rollout

That keeps initial enrollment manual and explicit, while making normal
post-enrollment management a standard flake deployment workflow.

### Leader Root Access

Trusted leader-machine deployer keys now live under:

```text
inventory/keys/leaders/
```

The base SSH layer reads every regular file in that directory and merges those
keys into `users.users.root.openssh.authorizedKeys.keys` on every host.

That means trusted leader machines can act as Colmena or deploy-rs deployers
against the whole fleet, including each other.
