# `storage/bitlocker`

Declarative BitLocker auto-unlock and mount support for workstation hosts.

## Inventory Shape

Declare volumes under `org.storage.bitlocker.volumes` on the host:

```nix
org.storage.bitlocker.volumes = {
  hydrus = {
    device = "/dev/disk/by-uuid/...";
    mapperName = "bitlk-hydrus";
    mountPoint = "/mnt/bitlocker/hydrus";
    keyFiles = [
      "/home/example/.config/bitlocker-recovery/E07B243F.recovery"
      "/home/example/.config/bitlocker-recovery/0EE6F93C.recovery"
    ];
  };
};
```

## Key Handling

- Keep recovery keys outside the repo and outside the Nix store.
- This dendrite reads recovery keys from host-local files such as
  `/home/example/.config/bitlocker-recovery/*.recovery`.
- Each key file should contain a single BitLocker recovery password.
- If the exact protector-to-volume mapping is unknown, list multiple `keyFiles`;
  the unlock unit will try them in order until one works.

## Mount Behavior

- Volumes are unlocked through `cryptsetup --type bitlk`.
- The decrypted NTFS filesystems are mounted through `systemd.mounts`.
- Use `readOnly = true;` for Windows OS volumes if you want a safer default
  while fast-startup or hibernation state is still a concern.
- If a volume is already mounted when its service starts, read-write volumes
  are remounted with the current declared options. This lets a deployment move
  a previously read-only mount to read-write without requiring a clean unmount.
