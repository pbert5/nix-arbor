{
  description = "Cluster identity registry MicroVM integration test";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    microvm = {
      url = "github:microvm-nix/microvm.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      microvm,
    }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      clusterctl = pkgs.callPackage ../../tools/clusterctl/clusterctl-package.nix { };
      mkNode =
        name: role:
        nixpkgs.lib.nixosSystem {
          inherit system;
          modules = [
            microvm.nixosModules.microvm
            (import ./microvm-test.nix {
              inherit clusterctl name role;
            })
          ];
        };
      nodes = {
        leader-a = mkNode "leader-a" "leader-a";
        leader-b = mkNode "leader-b" "leader-b";
        follower = mkNode "follower" "follower";
        ipfs-publisher = mkNode "ipfs-publisher" "ipfs-publisher";
        ipfs-follower = mkNode "ipfs-follower" "ipfs-follower";
        pubsub = mkNode "pubsub" "pubsub";
      };
      test = pkgs.writeShellApplication {
        name = "cluster-identity-microvm-test";
        runtimeInputs = [
          pkgs.coreutils
          pkgs.jq
          pkgs.kubo
          pkgs.openssh
          pkgs.python3
        ];
        text = ''
          set -euo pipefail

          shared=/tmp/cluster-identity-microvm
          rm -rf "$shared"
          install -d -m 0777 \
            "$shared" \
            "$shared/keys" \
            "$shared/registry" \
            "$shared/ipfs-repo" \
            "$shared/ipfs-xdg" \
            "$shared/ipfs-xdg/ipfs" \
            "$shared/ipfs-xdg/ipfs/denylists" \
            "$shared/pubsub-follower-repo" \
            "$shared/pubsub-follower-xdg" \
            "$shared/pubsub-follower-xdg/ipfs" \
            "$shared/pubsub-follower-xdg/ipfs/denylists" \
            "$shared/pubsub-publisher-repo"

          ssh-keygen -q -t ed25519 -N "" -f "$shared/keys/leader-a"
          ssh-keygen -q -t ed25519 -N "" -f "$shared/keys/leader-b"
          chmod 0600 "$shared/keys/leader-a" "$shared/keys/leader-b"

          export IPFS_PATH="$shared/keygen-repo"
          ipfs init --empty-repo >/dev/null
          ipns_name=$(ipfs key gen --type=ed25519 cluster-identity-leader-a)
          ipfs key export \
            --format=pem-pkcs8-cleartext \
            --output="$shared/keys/leader-a-ipns.pem" \
            cluster-identity-leader-a >/dev/null
          chmod 0600 "$shared/keys/leader-a-ipns.pem"
          unset IPFS_PATH

          SHARED="$shared" IPNS_NAME="$ipns_name" python - <<'PY'
          import json
          import os
          from pathlib import Path

          shared = Path(os.environ["SHARED"])
          leaders = {}
          for leader in ["leader-a", "leader-b"]:
              leaders[leader] = {
                  "canWrite": True,
                  "publicSigningKey": (shared / "keys" / f"{leader}.pub").read_text().strip(),
                  "ipnsName": os.environ["IPNS_NAME"] if leader == "leader-a" else None,
              }
          policy = {
              "clusterId": "microvm-test",
              "hostName": "follower",
              "localStatePath": "/shared/follower-state",
              "registry": {
                  "snapshotPath": "/shared/ipfs-snapshot",
                  "publisherStatePath": "/shared/publisher-state",
                  "ipfs": {
                      "api": "/unix/run/ipfs.sock",
                      "keyName": "cluster-identity-leader-a",
                      "ipnsLifetime": "1h",
                      "ipnsTtl": "1m",
                  },
              },
              "trustedLeaders": leaders,
              "policy": {
                  "policyGeneration": 1,
                  "allowPlaceholderSignatures": False,
                  "requireReceiptBeforePromote": True,
                  "burnedAlwaysWins": True,
                  "sameGenerationConflict": "freeze-subject",
                  "allowRollback": False,
                  "thresholds": {
                      "hostAgeRotation": 2,
                      "leaderPolicyUpdate": 2,
                  },
              },
          }
          (shared / "policy.json").write_text(json.dumps(policy, sort_keys=True) + "\n")

          pubsub = {
              "enable": True,
              "topic": "cluster-identity/microvm-test/roots/v1",
              "maxHintAgeSeconds": 600,
              "maxFutureSkewSeconds": 60,
              "maxMessageBytes": 65536,
              "publishTimeoutSeconds": 15,
              "reconnectDelaySeconds": 1,
          }
          publisher_policy = json.loads(json.dumps(policy))
          publisher_policy["registry"]["snapshotPath"] = "/shared/pubsub-snapshot"
          publisher_policy["registry"]["publisherStatePath"] = "/shared/pubsub-publisher-state"
          publisher_policy["registry"]["transports"] = {"pubsub": True}
          publisher_policy["registry"]["pubsub"] = pubsub
          publisher_policy["registry"]["ipfs"]["api"] = "/ip4/127.0.0.1/tcp/5002"
          follower_policy = json.loads(json.dumps(publisher_policy))
          follower_policy["hostName"] = "pubsub-follower"
          follower_policy["localStatePath"] = "/shared/pubsub-follower-state"
          follower_policy["registry"]["ipfs"]["api"] = "/unix/run/ipfs.sock"
          (shared / "pubsub-publisher-policy.json").write_text(
              json.dumps(publisher_policy, sort_keys=True) + "\n"
          )
          (shared / "pubsub-follower-policy.json").write_text(
              json.dumps(follower_policy, sort_keys=True) + "\n"
          )
          PY

          run_node() {
            local name=$1
            local runner=$2
            echo "==> booting $name"
            "$runner"
          }

          run_node leader-a ${nodes.leader-a.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/leader-a-gen-1"
          run_node follower ${nodes.follower.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/follower-first"
          test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' "$shared/out/rotations.json")" = replacement-pending
          run_node leader-a ${nodes.leader-a.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/leader-a-gen-2"
          run_node leader-b ${nodes.leader-b.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/leader-b-gen-2"
          run_node follower ${nodes.follower.config.microvm.declaredRunner}/bin/microvm-run

          test -f "$shared/success"
          test "$(jq -r '.nodes["node-a"].yggdrasil.generation' "$shared/out/active.json")" = 1
          test "$(jq -r '.subjects["node-a/yggdrasil"].generation' "$shared/out/conflicts.json")" = 2
          test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' "$shared/out/rotations.json")" = awaiting-acknowledgements
          run_node leader-a ${nodes.leader-a.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/leader-a-resolved"
          test -f "$shared/registry/events/leader-a/000000000002.json"
          test -f "$shared/registry/events/leader-b/000000000001.json"
          run_node follower ${nodes.follower.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/supersedence-success"
          test -f "$shared/rotation-ready"
          test "$(jq -r '.nodes["node-a"].yggdrasil.generation' "$shared/out/active.json")" = 2
          test "$(jq -r '.nodes["node-a"].yggdrasil.public.yggdrasilAddress' "$shared/out/active.json")" = "200::2"
          test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' "$shared/out/rotations.json")" = ready-to-retire
          test "$(jq -r '.subjects | length' "$shared/out/conflicts.json")" = 0
          run_node ipfs-publisher ${nodes.ipfs-publisher.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/ipfs-success"
          test "$(jq -r .eventChainTip.leaderSeq "$shared/ipfs-snapshot/root.json")" = 5
          test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' "$shared/ipfs-snapshot/state/rotations.json")" = ready-to-retire
          run_node ipfs-follower ${nodes.ipfs-follower.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/ipfs-follower-success"
          test "$(jq -r '.nodes["node-a"].yggdrasil.generation' "$shared/ipfs-follower-out/active.json")" = 2
          test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' "$shared/ipfs-follower-out/rotations.json")" = ready-to-retire
          test "$(jq -r '.heads["leader-a"].cid' "$shared/follower-state/checkpoint.json")" = \
            "$(jq -r .rootCid "$shared/publisher-state/leader-a.json")"
          run_node pubsub ${nodes.pubsub.config.microvm.declaredRunner}/bin/microvm-run
          test -f "$shared/pubsub-success"
          test -f "$shared/pubsub-fetch-triggered"
          echo "MicroVM registry conflict test passed"
          echo "MicroVM identity rotation state test passed"
          echo "MicroVM IPFS/IPNS publication test passed"
          echo "MicroVM IPNS follower convergence test passed"
          echo "MicroVM signed PubSub hint test passed"
        '';
      };
    in
    {
      nixosConfigurations = nodes;
      packages.${system} = {
        inherit test;
        leader-a = nodes.leader-a.config.microvm.declaredRunner;
        leader-b = nodes.leader-b.config.microvm.declaredRunner;
        follower = nodes.follower.config.microvm.declaredRunner;
        ipfs-publisher = nodes.ipfs-publisher.config.microvm.declaredRunner;
        ipfs-follower = nodes.ipfs-follower.config.microvm.declaredRunner;
        pubsub = nodes.pubsub.config.microvm.declaredRunner;
        default = test;
      };
      apps.${system}.test = {
        type = "app";
        program = "${test}/bin/cluster-identity-microvm-test";
      };
    };
}
