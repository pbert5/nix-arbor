# Local Registry canary

This preparation starts a local Registry and transport on r640-0 and eVolver. It does not open a network listener, enroll peers, or establish a cluster. Private Ygg remains dormant. The status timer is masked because its upstream probe exposes a token in process arguments.

The new `/var/lib/arbor-registry-canary-v1` and `/var/lib/arbor-registry-transport-canary-v1` paths are separate from historical state. Do not migrate, remove, or reuse the historical paths. The runtime uses `/run/arbor-registry` and `/run/arbor-registry-transport`; stop if either already exists or a Registry process is running. Do not print token or identity contents. Repeat all checks immediately before each host's test, with an independent console available. Keep existing fixture state intact.

On your management machine, use a clean checkout of the verified main revision and build both closures:

```sh
nix build --no-update-lock-file --no-link --print-out-paths .#nixosConfigurations.r640-0.config.system.build.toplevel
nix build --no-update-lock-file --no-link --print-out-paths .#nixosConfigurations.eVolver.config.system.build.toplevel
```

Record the output paths as `R640_CANDIDATE` and `EVOLVER_CANDIDATE`. Copy each closure to its host if needed: `nix copy --to ssh://r640-0 "$R640_CANDIDATE"` and `nix copy --to ssh://evolver "$EVOLVER_CANDIDATE"`. From the management machine, confirm fresh SSH works to each host, then open and retain separate interactive sessions:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes r640-0 hostname
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes evolver hostname
```

On each host separately, record the current and profile links and confirm they match; record these as `ROLLBACK`. Verify the path exists and has an executable `bin/switch-to-configuration`. Check normal controller health and confirm no other operator owns the host. Stop if any path exists, including a symlink, or if the services/processes are present. Confirm `/var/lib` and `/run` are normal writable directories with expected permissions. Check the full system change before activation. On eVolver, main also adds the existing repository-declared Madeline SSH key and Home Manager shell profile; inspect and accept that access change before continuing. Existing Ash and root grants must remain usable.

```sh
readlink -f /run/current-system
readlink -f /nix/var/nix/profiles/system
for p in /var/lib/arbor-registry-canary-v1 /var/lib/arbor-registry-transport-canary-v1 /run/arbor-registry /run/arbor-registry-transport; do
  if test -e "$p" || test -L "$p"; then stat -c '%n %F %U:%G %a' "$p"; else printf '%s absent\n' "$p"; fi
done
systemctl is-active sshd tailscaled NetworkManager
systemctl status arbor-registry.service arbor-registry-transport.service --no-pager
pgrep -f 'arbor-registry[d-]|yggdrasil' || true
sudo nix store diff-closures "$ROLLBACK" "$CANDIDATE"
```

Run the r640-0 canary first, setting `CANDIDATE` and `ROLLBACK` to the recorded paths on that host. `test` changes the running system and may write new persistent state, but does not change the system profile. Do not proceed to eVolver if any check fails.

```sh
sudo "$CANDIDATE/bin/switch-to-configuration" test
systemctl is-active arbor-registry.service arbor-registry-transport.service sshd tailscaled NetworkManager
systemctl is-enabled arbor-runtime-status.service arbor-runtime-status.timer
sudo ss -lntp
readlink -f /nix/var/nix/profiles/system
```

Confirm no Registry TCP listener, unchanged management and controller health, and fresh SSH from the management machine. The runtime adapter reads the token itself; never pass it in command arguments. On the host, obtain its executable from the running unit and inspect local identity before creating one:

```sh
runtime=$(systemctl show -p ExecStart --value arbor-registry.service | sed -n 's/.*path=\([^ ;]*\)\/bin\/arbor-registryd.*/\1/p')
printf '%s\n' '{"protocol":"arbor-manager/runtime-adapter","version":1,"operation":"identity/inspect","data":{}}' | sudo -u arbor-registry "$runtime/bin/arbor-registry-manager-adapter"
```

Stop if inspection reports an existing identity or any conflict. To initialize an isolated local identity, set `node=r640-0` on the first host or `node=eVolver` on the second:

```sh
printf '{"protocol":"arbor-manager/runtime-adapter","version":1,"operation":"identity/init-self","data":{"nodeId":"%s","domain":"nix-arbor-live-v1"}}\n' "$node" | sudo -u arbor-registry "$runtime/bin/arbor-registry-manager-adapter"
printf '{"protocol":"arbor-manager/runtime-adapter","version":1,"operation":"registry/summary","data":{"nodeId":"%s"}}\n' "$node" | sudo -u arbor-registry "$runtime/bin/arbor-registry-manager-adapter"
```

Verify generation one, self-rooted local genesis and no peers or parents. Record public fingerprints and verify they differ across hosts. Recheck SSH and application health. These local identities do not peer or grant cross-host authority.

To roll back the affected host, use its recorded running closure, not the booted closure. Keep the new state for inspection; do not start an older Registry implementation on it. Recheck fresh SSH and controller health afterward.

```sh
sudo systemctl stop arbor-participant.target arbor-registry.service arbor-registry-transport.service
sudo "$ROLLBACK/bin/switch-to-configuration" test
readlink -f /run/current-system
readlink -f /nix/var/nix/profiles/system
systemctl is-active sshd tailscaled NetworkManager
```

Before the test, compare the public managed SSH key files and relevant service definitions in the running and candidate systems. For example, on the target host:

```sh
for system in "$ROLLBACK" "$CANDIDATE"; do
  printf '\n%s\n' "$system"
  for user in ash root madeline; do
    file="$system/etc/ssh/authorized_keys.d/$user"
    if test -e "$file"; then printf '%s ' "$user"; sha256sum "$file"; else printf '%s absent\n' "$user"; fi
  done
  for unit in sshd tailscaled NetworkManager docker syncthing; do
    file="$system/etc/systemd/system/$unit.service"
    if test -e "$file"; then sha256sum "$file"; else printf '%s absent\n' "$unit"; fi
  done
done
```

Investigate every unexpected difference, including account and Home Manager activation changes, firewall, boot, storage and application services; a store-path diff alone does not establish operational equivalence. On eVolver the known Madeline managed key and profile addition can persist changes to her home even after `test` rollback. Stop if you cannot review or accept those effects. Never remove an existing authorized key to make a canary pass.
