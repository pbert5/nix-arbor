# r640-0 eVolver access

This is the public access record for the cluster-leader path:

| Field | Value |
| --- | --- |
| OpenSSH alias | `eVolver` |
| Yggdrasil address | `200:c739:8dc3:8e5a:b1b4:bf7b:1142:d29a` |
| SSH principal | `root` |
| Credential ID | `r640-0-leader-user-ssh` |
| Destination | `/home/ash/.ssh/cluster-leader-ed25519` |
| Expected public-key fingerprint | `SHA256:Z2waeID+mQXjRQBBB2rp0OAPnFYK7Q57QJvnyAMvkiU` |

The Nix configuration publishes only the alias, address, principal, and path.
The private key is an operator-provisioned external file. It must not be
committed, placed in `.env`, evaluated by Nix, or copied into the Nix store.

## Controlled materialization

Perform these steps on the intended `r640-0` operator host, using the approved
secret manager for the credential ID. Do not print the credential, put it in a
shell argument, or capture it in logs.

1. Confirm the target host and destination before retrieving anything:

   ```sh
   test "$(hostname)" = r640-0
   install -d -m 0700 /home/ash/.ssh
   ```

2. Retrieve credential `r640-0-leader-user-ssh` directly into the destination
   using the secret manager's protected-file/API mechanism. The provider-specific
   command is intentionally omitted; its output must be the OpenSSH private key
   at `/home/ash/.ssh/cluster-leader-ed25519`, with no plaintext intermediate in
   the repository or Nix store.

3. Apply ownership and permissions, then verify the derived public key without
   exposing private contents:

   ```sh
   chown ash:users /home/ash/.ssh/cluster-leader-ed25519
   chmod 0400 /home/ash/.ssh/cluster-leader-ed25519
   test "$(ssh-keygen -y -f /home/ash/.ssh/cluster-leader-ed25519 \
     | ssh-keygen -lf - | awk '{print $2}')" = \
     SHA256:Z2waeID+mQXjRQBBB2rp0OAPnFYK7Q57QJvnyAMvkiU
   ```

   Stop and quarantine the file if the fingerprint does not match. Never
   replace the expected fingerprint based on a failed check.

4. Verify the rendered alias locally with `ssh -G eVolver`. Separately verify
   the eVolver host key through the normal trusted host-key process; the
   fingerprint above identifies the user key, not the server host key.

5. Only after those checks, an authorized operator may perform a bounded
   acceptance login:

   ```sh
   ssh -o BatchMode=yes -o StrictHostKeyChecking=ask eVolver true
   ```

   This procedure does not authorize a deployment, configuration switch,
   reboot, hardware change, or other remote action. Keep any failed connection
   evidence and stop for review.

## Current validation boundary

This worktree has no private credential and does not authenticate or actuate
the physical R640/eVolver host. A read-only route check and unauthenticated
TCP/22 probe from the validation environment succeeded. The pure metadata test
validates the alias and path only; server host-key verification and the final
authenticated login remain operator-side acceptance steps because the required
credential is unavailable here.
