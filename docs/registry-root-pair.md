# Pair the existing r640-0 and eVolver Registry roots

This operation records one directed parent relationship, from `r640-0` to `eVolver`. Each Registry keeps its existing generation-one identity, local signing key and genesis. Both operators approve the same identities, realm and direction on their respective consoles. The resulting certificate binds both roots and the pairing channel. Its authority covers this relationship only. Ongoing synchronization, network membership and attestation require separate mechanisms.

## Prepare both hosts

Use the reviewed Nix Arbor checkout and the exact Registry component commit supplied in the implementation handoff. The root flake pins the reviewed Registry candidate; verify the lock before building. Build both host systems on the management machine from an archive of the selected commit. The override applies to the daemon, transport module and installed CLI on each host.

```bash
: "${REGISTRY_REPO:?set to the local arbor-registry checkout}"
: "${REGISTRY_REV:?set to the full reviewed component commit SHA}"
(
  set -euo pipefail
  test "$(git -C "$REGISTRY_REPO" rev-parse "$REGISTRY_REV^{commit}")" = "$REGISTRY_REV"
  src=$(mktemp -d)
  trap 'rm -rf -- "$src"' EXIT
  git -C "$REGISTRY_REPO" archive "$REGISTRY_REV" | tar -x -C "$src"
  for host in r640-0 eVolver; do
    nix build --override-input arbor-registry "path:$src" --no-write-lock-file \
      --out-link "result-pair-$host" ".#nixosConfigurations.$host.config.system.build.toplevel"
    test -x "result-pair-$host/sw/bin/arbor-registry-pair"
    readlink -f "result-pair-$host"
  done
)
```

Before any separately approved upgrade or rollback, stop both Registry and transport services on each affected host and verify the old transport process has exited. The new service gives transport a separate account; a surviving old transport still has access to Registry signing state. Preserve both state directories. Verify state paths do not overlap through symlinks or mounts. Custom IPC parents must be owned by the corresponding service account, with trusted non-writable ancestors; an existing custom token must be owned by the Registry account with group arbor-registry and mode 0640. Stop both daemons before preparing those paths, and never regenerate a token cached by a running daemon.

Under the normal host change approval, copy each closure to its corresponding host with `nix copy --to ssh://HOST CLOSURE`, using the existing verified SSH alias. On that host, record the current system path, review `nix store diff-closures /run/current-system CLOSURE` and deploy that exact closure through the normal NixOS system-profile workflow. For an approved temporary activation, `sudo CLOSURE/bin/switch-to-configuration test` uses the new services until the next system switch or reboot. Require matching deployments and healthy services on **both** machines before pairing. Preserve the Registry state directories and local keys during upgrades and recovery.

On each trusted console, run the following from the reviewed root checkout. Record each node's public fingerprint and exchange the expected fingerprints over an independently authenticated channel. Each host must have its own distinct fingerprint, local genesis, generation one, and the expected hostname. For a new relationship, both have zero parents and peers.

```sh
tools/arbor/registry status "$(hostname)"
tools/arbor/registry inspect "$(hostname)"
sudo -u arbor-registry -- /run/current-system/sw/bin/arbor-registry-pair status \
  --parent r640-0 --child eVolver --config /etc/arbor-registry/config.json
```

## Approve the relationship

1. At the r640-0 console, start the parent command below. Read the one-time pairing code to the intended eVolver operator over a private, authenticated channel.
2. At the eVolver console, start the child command and enter the parent's code at the hidden terminal prompt. Keep the code out of shell arguments, chat logs and tickets.
3. At **both** consoles, compare the displayed fingerprints to the independently recorded values and confirm the common realm is `nix-arbor-live-v1`. Verify the parent is r640-0 and the child is eVolver. Approve only if all values agree. Cancel on a mismatch.
4. Record the public certificate digest reported on each console. Both digests must match.

Parent command on r640-0:

```sh
sudo -u arbor-registry -- /run/current-system/sw/bin/arbor-registry-pair parent \
  --parent r640-0 --child eVolver --config /etc/arbor-registry/config.json
```

Child command on eVolver:

```sh
sudo -u arbor-registry -- /run/current-system/sw/bin/arbor-registry-pair child \
  --parent r640-0 --child eVolver --config /etc/arbor-registry/config.json
```

Both machines require outbound access to the same Magic Wormhole mailbox relay. To use an operator-managed relay, supply the same `--relay-url URL` on each pairing command. Registry IPC remains local to each machine. The CLI reads the socket credential under the Registry service account.

## Verify or resume

Repeat the local `status --parent r640-0 --child eVolver` command on **both** hosts. Expect `paired: true` and identical certificate digests. Run `tools/arbor/registry summary "$(hostname)"` at each console. Both local fingerprints and genesis values must match the preflight. r640-0 has zero incoming parents, eVolver has one, and both have zero peers. The counts alone cannot identify the counterpart.

If the exchange is interrupted, check both local statuses. Parent approval can reserve the two identities and direction before delivery. If one or neither reports the pair, repeat the parent and child commands with a fresh code and compare both readbacks. Keep any conflicting certificate or identity state for investigation. Reinitializing a root would change the evidence needed to verify the relationship.

The signed exchange follows the two-console approval pattern in the pinned [flake-devbox enrollment guide](https://github.com/pbert5/flake-devbox/blob/c9aec10d5610a86473324812737bab05510ee521/docs/cluster-ops/cluster-management/adding-nodes.md). Here both signers already have a local genesis.
