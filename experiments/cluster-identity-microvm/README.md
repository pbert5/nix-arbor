# Cluster Identity MicroVM Test

This isolated experiment boots three QEMU MicroVM roles against a shared test
registry, then boots a Kubo publisher, a fresh IPNS follower, and a Phase 4
PubSub role with two independent Kubo repositories. It verifies that:

1. leader A publishes generation 1 and the follower accepts it
2. leader A and leader B publish different generation 2 payloads
3. the follower keeps generation 1 as last-good state
4. the follower materializes the generation 2 conflict
5. leader A appends a signed supersedence record selecting its generation 2
   entry without modifying either conflicting entry
6. a signed rotation intent for generation 1 materializes as
   `replacement-pending`, then `awaiting-acknowledgements`
7. the follower accepts leader A's generation 2 entry, clears the conflict,
   writes a signed rotation acknowledgement, and materializes `ready-to-retire`
8. the publisher builds an exhaustive signed snapshot and adds it to IPFS
9. the signed root records the rotation- and supersedence-bearing event-chain
   tip
10. the enrolled IPNS name resolves to the published CID
11. `root.json` can be read by CID and the snapshot passes local verification
12. the follower resolves the trusted IPNS name and fetches the immutable root
13. the follower pins the CID, records its head checkpoint, and materializes
   only the leader-authored generation 2 state
14. the published and fetched materialized state includes the rotation view
15. two independent Kubo nodes establish a PubSub topic mesh inside a MicroVM
16. a successful snapshot publication emits a signed root hint
17. the listener verifies that hint and starts the configured systemd fetch
    probe without treating the hint as authoritative registry state

Run it with:

```bash
nix run ./experiments/cluster-identity-microvm#test
```

Test-only OpenSSH and IPNS keys are generated under
`/tmp/cluster-identity-microvm` for each run. No test private keys enter the Nix
store or repository. The test uses offline IPNS resolution so it does not
depend on the public DHT.

The publisher and follower share a Kubo repository over virtio-9p. Because
that filesystem cannot emulate guest ownership or chmod for Kubo's service UID,
the two isolated test VMs run Kubo as root with XDG state redirected into the
shared test directory. Production NixOS configurations continue to use Kubo's
normal dedicated service account and managed data directory.

The Phase 4 role does not reuse that repository. It runs a system-managed
follower Kubo node and a separate publisher Kubo daemon, connects their swarm
addresses over guest loopback, and transfers the signed announcement over the
real Kubo PubSub CLI.
