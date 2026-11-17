# Raspberry-evolver host notes

The bootstrap timer makes up to three serialized attempts per activation, with
10- and 20-second pauses, and schedules another activation after two minutes.
An ambiguous result keeps the key and can be retried, including after reboot.
A successful registration followed by lost local identity can consume a
single-use key; this design does not guarantee exactly one node or eliminate
orphaned registrations. `enrolled` means the daemon reports an authenticated
local identity with no outstanding Tailnet Lock approval; it does not prove
current connectivity or that state has reached durable storage.

`pending-approval` requires tailnet administrator approval or a Tailnet Lock
signature. `needs-new-key` is reported only for the pinned client's explicit
invalid-authkey response; unavailable or ambiguous state is `indeterminate`.
An expired, revoked or consumed key may require a fresh appropriate key even
when no definitive error is available. Never remove Tailscale's state to retry.

When LAN SSH is available, securely replace the key as follows from an
operator's Bash terminal; replace `raspberry-evolver` with its reachable LAN
address if necessary. The prompt does not echo, and the key is sent on SSH stdin
rather than in command arguments. This assumes the installed `ash` public SSH
key and its configured administrative access.

```bash
read -rs -p 'New Tailscale auth key: ' key; printf '\n'
printf '%s' "$key" | ssh -T ash@raspberry-evolver \
  'sudo install -d -m 0700 /var/lib/raspberry-evolver/bootstrap && sudo install -m 0600 /dev/stdin /var/lib/raspberry-evolver/bootstrap/.replacement && sudo mv -f /var/lib/raspberry-evolver/bootstrap/.replacement /var/lib/raspberry-evolver/bootstrap/tailscale.authkey'
unset key
```

The timer detects replacement and retries; `sudo systemctl start
raspberry-evolver-bootstrap.service` can trigger it sooner. If SSH is
unavailable, power down the Pi, mount the card's ext4 root on a trusted Linux
machine and replace `var/lib/raspberry-evolver/bootstrap/tailscale.authkey`
within that mount using a root-owned 0600 file in a root-owned 0700 directory;
do not place the key on the firmware partition. A copied image containing the
key remains sensitive. Use a new key as appropriate and preserve the existing
Tailscale state. Confirm the intended tailnet separately.

Weekly Nix GC uses `--delete-older-than 14d`. It can prune generations in all
writable profiles discovered by Nix, not just the system profile, and does not
promise a fixed rollback count. The running and booted system closures and
valid independent GC roots remain protected, but closure roots do not preserve
the associated generation link or boot-menu entry. Avoid concurrent manual
profile surgery. This policy neither caps future data nor guarantees a maximum
store size; image build and copies belong on the builder, not the Pi.
