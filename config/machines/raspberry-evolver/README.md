# Raspberry-evolver host notes

Place one raw key in `tailscale-authkey.txt` on the Windows-readable FIRMWARE
partition. The Pi mounts it at `/boot/firmware`. The service stages the value
as a root-only file and gives Tailscale its path. It allows up to three attempts
per activation with 10- and 20-second pauses, up to three activations per key
per boot. Definitive rejections are remembered across reboot. Replace a
rejected key on the firmware partition with the Pi powered off.

Check `/run/raspberry-evolver/bootstrap.status` over LAN SSH. With late network
after `retry-limit`, reboot to retry, or run
`sudo tailscale up --accept-dns=false` for interactive enrollment. With
`pending-approval`, check tailnet administrator approval or Tailnet Lock.
An expired or consumed one-use key with lost node identity can require a new
key. Preserve Tailscale state.

`enrolled-cleanup-failed` means local authenticated identity was confirmed and
the credential copies could not both be removed. Retry cleanup after restoring
access to the firmware mount. Keep any SD card with a leftover key private.
FAT stores the key as plaintext, and deletion is not secure erasure.

Weekly Nix GC uses `--delete-older-than 14d`. It can prune generations in all
writable profiles discovered by Nix, not just the system profile, and does not
promise a fixed rollback count. The running and booted system closures and
valid independent GC roots remain protected, but closure roots do not preserve
the associated generation link or boot-menu entry. Avoid concurrent manual
profile surgery. This policy neither caps future data nor guarantees a maximum
store size; image build and copies belong on the builder, not the Pi.
