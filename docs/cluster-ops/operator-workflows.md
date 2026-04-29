# Operator Workflows

This page is the practical "what do I do next" guide.

## Workflow: Check Whether A Host Is Ready For Bootstrap

1. confirm the host has an entry in
   [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix)
2. confirm `inventory/host-bootstrap.nix` has a usable `targetHost`
3. verify root SSH from a trusted leader
4. run `bootstrap-host --dry-run`

## Workflow: Enroll A Host

1. run the dry run first
2. verify the discovered public key and Ygg address look stable
3. rerun without `--dry-run`
4. decide whether to keep deployment on bootstrap transport or promote it to
   `privateYggdrasil`
5. deploy the host

## Workflow: Switch A Host To Ygg Deployment

1. confirm the host has enrolled `address` and `publicKey`
2. set or confirm `deploymentTransport = "privateYggdrasil"`
3. inspect the generated deploy target with
   `nix eval '.#deploy.nodes.<host>' --json`
4. deploy with `deploy-rs`

## Workflow: Roll Out A New Trusted Peer Relationship

1. enroll any hosts whose identities are still missing
2. deploy the newly enrolled host
3. deploy the hosts that should trust or peer with it
4. only after that consider stricter Ygg contact restrictions

## Workflow: Add A New Leader Machine

1. ensure the host is itself managed and reachable
2. add its deployer public key under `inventory/keys/leaders/`
3. mark it `operatorCapable = true` in
   [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
4. deploy the fleet so every node receives the new root authorized key

## Workflow: Read A `deploy-rs` Success

Healthy signs:

- the profile block shows the expected hostname
- activation succeeded
- the canary file was seen
- deployment confirmed

If the hostname is the Ygg address, the generated deploy surface is already
preferring Ygg transport.
