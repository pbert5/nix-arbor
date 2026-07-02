{
  clusterctl,
  name,
  role,
}:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  usesKubo = builtins.elem role [
    "ipfs-publisher"
    "ipfs-follower"
    "pubsub"
  ];
  publish =
    leader: generation: address: ''
      PYTHONPATH=${../../tools/clusterctl} ${pkgs.python3}/bin/python - \
        ${leader} ${toString generation} ${address} <<'PY'
      import sys
      from pathlib import Path

      from clusterctl.events import write_json
      from clusterctl.registry import canonical_event_path, finalize_event
      from clusterctl.signing import key_fingerprint, public_key_from_private, sign_record

      leader, generation_text, address = sys.argv[1:]
      generation = int(generation_text)
      registry = Path("/shared/registry")
      signing_key = Path("/shared/keys") / leader
      public_key = public_key_from_private(signing_key)
      event = {
          "schema": "cluster.identity.event.v1",
          "clusterId": "microvm-test",
          "eventId": f"{leader}-{generation}-{address}",
          "leader": leader,
          "leaderKeyId": key_fingerprint(public_key),
          "policyGeneration": 1,
          "subject": {"node": "node-a", "service": "yggdrasil"},
          "generation": generation,
          "state": "active",
          "public": {
              "yggdrasilPublicKey": f"key-{address}",
              "yggdrasilAddress": address,
              "fingerprint": f"sha256:{leader}-{generation}-{address}",
          },
          "privateDelivery": None,
          "supersedes": [],
          "createdAt": f"2026-06-23T00:00:{generation:02d}Z",
      }
      finalize_event(registry, event)
      event["signature"] = sign_record(event, signing_key)
      write_json(canonical_event_path(registry, event), event)
      PY
    '';
  publishSshHost =
    leader: ''
      PYTHONPATH=${../../tools/clusterctl} ${pkgs.python3}/bin/python - \
        ${leader} <<'PY'
      import sys
      from pathlib import Path

      from clusterctl.events import write_json
      from clusterctl.registry import canonical_event_path, finalize_event
      from clusterctl.signing import key_fingerprint, public_key_from_private, sign_record

      leader = sys.argv[1]
      registry = Path("/shared/registry")
      signing_key = Path("/shared/keys") / leader
      public_key = public_key_from_private(signing_key)
      event = {
          "schema": "cluster.identity.event.v1",
          "clusterId": "microvm-test",
          "eventId": f"{leader}-ssh-host-1",
          "leader": leader,
          "leaderKeyId": key_fingerprint(public_key),
          "policyGeneration": 1,
          "subject": {"node": "node-a", "service": "ssh-host"},
          "generation": 1,
          "state": "active",
          "public": {
              "sshHostKey": public_key,
              "fingerprint": f"sha256:{leader}-ssh-host-1",
          },
          "privateDelivery": None,
          "supersedes": [],
          "createdAt": "2026-06-23T00:00:01Z",
      }
      finalize_event(registry, event)
      event["signature"] = sign_record(event, signing_key)
      write_json(canonical_event_path(registry, event), event)
      PY
    '';
  appendRotationIntent =
    leader: ''
      PYTHONPATH=${../../tools/clusterctl} ${pkgs.python3}/bin/python - \
        ${leader} <<'PY'
      import sys
      from pathlib import Path

      from clusterctl.events import read_json, write_json
      from clusterctl.registry import ROTATION_SCHEMA, canonical_event_path, finalize_rotation
      from clusterctl.signing import key_fingerprint, public_key_from_private, sign_record

      leader = sys.argv[1]
      registry = Path("/shared/registry")
      signing_key = Path("/shared/keys") / leader
      public_key = public_key_from_private(signing_key)
      target = next(
          event
          for path in sorted((registry / "events").glob("*/*.json"))
          for event in [read_json(path, {})]
          if event.get("schema") == "cluster.identity.event.v1"
          and event.get("subject") == {"node": "node-a", "service": "yggdrasil"}
          and event.get("generation") == 1
      )
      record = {
          "schema": ROTATION_SCHEMA,
          "clusterId": "microvm-test",
          "rotationId": "rotation-yggdrasil-gen1",
          "eventId": "rotation-yggdrasil-gen1-intent",
          "leader": leader,
          "leaderKeyId": key_fingerprint(public_key),
          "policyGeneration": 1,
          "mode": "graceful",
          "reason": "MicroVM graceful generation 1 rotation",
          "trigger": {"kind": "microvm-test", "hosts": ["node-a"]},
          "targets": [
              {
                  "node": "node-a",
                  "service": "yggdrasil",
                  "generation": target["generation"],
                  "eventHash": target["eventHash"],
                  "fingerprint": target["public"]["fingerprint"],
                  "exposureReason": "MicroVM test target",
              }
          ],
          "acknowledgementPolicy": {
              "minimum": 1,
              "requiredNodes": ["node-a"],
              "deadline": "2026-07-07T00:00:00Z",
          },
          "transportOrder": [],
          "createdAt": "2026-06-23T00:00:02Z",
      }
      finalize_rotation(registry, record)
      record["signature"] = sign_record(record, signing_key)
      write_json(canonical_event_path(registry, record), record)
      PY
    '';
  appendRotationAcknowledgement = ''
    PYTHONPATH=${../../tools/clusterctl} ${pkgs.python3}/bin/python - <<'PY'
    from pathlib import Path

    from clusterctl.events import read_json, write_json
    from clusterctl.registry import ROTATION_ACK_SCHEMA
    from clusterctl.signing import key_fingerprint, public_key_from_private, sign_record

    shared = Path("/shared")
    registry = shared / "registry"
    signing_key = shared / "keys" / "leader-a"
    public_key = public_key_from_private(signing_key)
    replacement = next(
        event
        for path in sorted((registry / "events").glob("*/*.json"))
        for event in [read_json(path, {})]
        if event.get("schema") == "cluster.identity.event.v1"
        and event.get("leader") == "leader-a"
        and event.get("subject") == {"node": "node-a", "service": "yggdrasil"}
        and event.get("generation") == 2
    )
    record = {
        "schema": ROTATION_ACK_SCHEMA,
        "clusterId": "microvm-test",
        "rotationId": "rotation-yggdrasil-gen1",
        "node": "node-a",
        "replacementEventHashes": [replacement["eventHash"]],
        "acceptedRootCid": "microvm-local-root",
        "acceptedAt": "2026-06-23T00:05:00Z",
        "signedByNode": {
            "type": "ssh-host-ed25519",
            "publicKey": public_key,
            "keyId": key_fingerprint(public_key),
        },
    }
    record["signature"] = sign_record(record, signing_key)
    write_json(registry / "receipts" / "node-a" / "rotation-yggdrasil-gen1.ack.json", record)
    PY
  '';
  action =
    if role == "pubsub" then
      ''
        publisher_repo=/shared/pubsub-publisher-repo
        publisher_policy=/shared/pubsub-publisher-policy.json
        follower_policy=/shared/pubsub-follower-policy.json
        export IPFS_TELEMETRY=off

        export IPFS_PATH="$publisher_repo"
        ipfs init --empty-repo >/dev/null
        ipfs config --json Pubsub.Enabled true
        ipfs config Addresses.API /ip4/127.0.0.1/tcp/5002
        ipfs config Addresses.Gateway /ip4/127.0.0.1/tcp/8181
        ipfs config --json Addresses.Swarm '["/ip4/127.0.0.1/tcp/4101"]'
        ipfs daemon >/shared/pubsub-publisher-daemon.log 2>&1 &
        unset IPFS_PATH

        for _ in $(seq 1 100); do
          if IPFS_PATH="$publisher_repo" ipfs id >/dev/null 2>&1; then
            break
          fi
          sleep 0.1
        done
        IPFS_PATH="$publisher_repo" ipfs id >/dev/null

        publisher_addr=$(IPFS_PATH="$publisher_repo" ipfs id -f='<addrs>\n' | head -1)
        ipfs --api=/unix/run/ipfs.sock swarm connect "$publisher_addr" >/dev/null

        clusterctl registry listen-pubsub \
          --policy "$follower_policy" \
          --trigger-unit pubsub-fetch-probe.service \
          >/shared/pubsub-listener.log 2>&1 &

        topic=$(jq -r .registry.pubsub.topic "$follower_policy")
        for _ in $(seq 1 100); do
          if IPFS_PATH="$publisher_repo" ipfs pubsub peers "$topic" | grep -q .; then
            break
          fi
          sleep 0.1
        done
        IPFS_PATH="$publisher_repo" ipfs pubsub peers "$topic" | grep -q .

        sleep 3
        PYTHONPATH=${../../tools/clusterctl} ${pkgs.python3}/bin/python - <<'PY'
        from pathlib import Path

        from clusterctl.announcements import publish_announcement
        from clusterctl.events import read_json, write_json
        from clusterctl.snapshot import build_snapshot

        shared = Path("/shared")
        policy = read_json(shared / "pubsub-publisher-policy.json", {})
        root = build_snapshot(
            shared / "registry",
            shared / "pubsub-snapshot",
            policy,
            "leader-a",
            shared / "keys/leader-a",
        )
        state = {
            "publisher": "leader-a",
            "rootCid": "bafyphasefourroot",
            "rootSequence": root["rootSequence"],
            "previousRootCid": root["previousRootCid"],
            "ipnsName": policy["trustedLeaders"]["leader-a"]["ipnsName"],
        }
        result = publish_announcement(
            policy,
            state,
            root,
            shared / "keys/leader-a",
        )
        if result.get("status") != "published":
            raise RuntimeError(result)
        write_json(shared / "pubsub-publish.json", result)
        PY

        jq -e '.status == "published"' /shared/pubsub-publish.json >/dev/null
        for _ in $(seq 1 100); do
          if [ -e /shared/pubsub-fetch-triggered ]; then
            break
          fi
          sleep 0.1
        done
        test -e /shared/pubsub-fetch-triggered
        jq -e \
          '.connectionState == "subscribed" and .accepted == 1 and .lastResult == "fetch-triggered"' \
          /shared/pubsub-follower-state/pubsub-status.json >/dev/null
        touch /shared/pubsub-success
        systemctl poweroff --no-block
      ''
    else if role == "ipfs-follower" then
      ''
        clusterctl registry fetch-ipfs \
          --policy /shared/policy.json \
          --out /shared/ipfs-follower-out \
          --cache-dir /shared/follower-cache \
          --accepted-registry /shared/accepted-registry

        cid=$(jq -r .rootCid /shared/publisher-state/leader-a.json)
        test "$(jq -r '.heads["leader-a"].cid' /shared/follower-state/checkpoint.json)" = "$cid"
        test "$(jq -r '.nodes["node-a"].yggdrasil.generation' /shared/ipfs-follower-out/active.json)" = 2
        test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' /shared/ipfs-follower-out/rotations.json)" = "ready-to-retire"
        ipfs --api=/unix/run/ipfs.sock pin ls --type=recursive "$cid" >/dev/null
        touch /shared/ipfs-follower-success
      ''
    else if role == "ipfs-publisher" then
      ''
        clusterctl registry ipns-key ensure \
          --policy /shared/policy.json \
          --publisher leader-a \
          --key-name cluster-identity-leader-a \
          --key-file /shared/keys/leader-a-ipns.pem
        clusterctl registry publish-ipfs \
          --registry /shared/registry \
          --snapshot-dir /shared/ipfs-snapshot \
          --policy /shared/policy.json \
          --publisher leader-a \
          --signing-key /shared/keys/leader-a

        cid=$(jq -r .rootCid /shared/publisher-state/leader-a.json)
        ipns_name=$(jq -r '.trustedLeaders["leader-a"].ipnsName' /shared/policy.json)
        test "$(ipfs --api=/unix/run/ipfs.sock name resolve --offline "/ipns/$ipns_name")" = "/ipfs/$cid"
        ipfs --api=/unix/run/ipfs.sock cat "/ipfs/$cid/root.json" | jq -e '.schema == "cluster.identity.root.v1"' >/dev/null
        test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' /shared/ipfs-snapshot/state/rotations.json)" = "ready-to-retire"
        clusterctl registry validate \
          --registry /shared/ipfs-snapshot \
          --policy /shared/policy.json
        touch /shared/ipfs-success
      ''
    else if role == "leader-a" then
      ''
        if [ -e /shared/leader-a-gen-2 ]; then
          winner=$(
            jq -r \
              'select(.schema == "cluster.identity.event.v1" and .leader == "leader-a" and .generation == 2) | .eventHash' \
              /shared/registry/events/leader-a/*.json
          )
          loser=$(
            jq -r \
              'select(.schema == "cluster.identity.event.v1" and .leader == "leader-b" and .generation == 2) | .eventHash' \
              /shared/registry/events/leader-b/*.json
          )
          clusterctl identity resolve \
            --registry /shared/registry \
            --out /shared/out \
            --policy /shared/policy.json \
            --winner-event "$winner" \
            --loser-event "$loser" \
            --reason "MicroVM manual resolution" \
            --signing-key /shared/keys/leader-a \
            --no-commit \
            --no-push
          touch /shared/leader-a-resolved
        elif [ -e /shared/leader-a-first ]; then
          ${publish "leader-a" 2 "200::2"}
          touch /shared/leader-a-gen-2
        else
          ${publish "leader-a" 1 "200::1"}
          ${publishSshHost "leader-a"}
          ${appendRotationIntent "leader-a"}
          touch /shared/leader-a-first
          touch /shared/leader-a-gen-1
        fi
      ''
    else if role == "leader-b" then
      ''
        ${publish "leader-b" 2 "200::dead"}
        touch /shared/leader-b-gen-2
      ''
    else
      ''
        clusterctl registry reconcile \
          --registry /shared/registry \
          --out /shared/out \
          --policy /shared/policy.json

        if [ -e /shared/leader-a-resolved ]; then
          test "$(jq -r '.nodes["node-a"].yggdrasil.generation' /shared/out/active.json)" = 2
          test "$(jq -r '.nodes["node-a"].yggdrasil.public.yggdrasilAddress' /shared/out/active.json)" = "200::2"
          test "$(jq -r '.subjects | length' /shared/out/conflicts.json)" = 0
          if [ ! -e /shared/rotation-ack-written ]; then
            ${appendRotationAcknowledgement}
            touch /shared/rotation-ack-written
            clusterctl registry reconcile \
              --registry /shared/registry \
              --out /shared/out \
              --policy /shared/policy.json
          fi
          test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' /shared/out/rotations.json)" = "ready-to-retire"
          touch /shared/rotation-ready
          touch /shared/supersedence-success
        else
          test "$(jq -r '.nodes["node-a"].yggdrasil.generation' /shared/out/active.json)" = 1
          if [ -e /shared/leader-a-gen-2 ]; then
            test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' /shared/out/rotations.json)" = "awaiting-acknowledgements"
          else
            test "$(jq -r '.rotations["rotation-yggdrasil-gen1"].status' /shared/out/rotations.json)" = "replacement-pending"
          fi
        fi
        if [ -e /shared/follower-first ] && [ ! -e /shared/leader-a-resolved ]; then
          test "$(jq -r '.subjects["node-a/yggdrasil"].generation' /shared/out/conflicts.json)" = 2
          touch /shared/success
        elif [ ! -e /shared/follower-first ]; then
          touch /shared/follower-first
        fi
      '';
in
{
  networking.hostName = name;
  system.stateVersion = "26.05";

  environment.systemPackages = [
    clusterctl
    pkgs.jq
  ];

  systemd.services.registry-scenario = {
    description = "Run the cluster identity MicroVM scenario step";
    wantedBy = [ "multi-user.target" ];
    after = [ "shared.mount" ] ++ lib.optional usesKubo "ipfs.service";
    requires = [ "shared.mount" ] ++ lib.optional usesKubo "ipfs.service";
    serviceConfig.Type = "oneshot";
    path = [
      clusterctl
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.jq
      pkgs.kubo
      pkgs.openssh
    ];
    script = ''
      set -euo pipefail
      export HOME=/root
      trap 'systemctl poweroff --no-block' EXIT
      ${action}
    '';
  };

  systemd.services.pubsub-fetch-probe = lib.mkIf (role == "pubsub") {
    description = "Record a Phase 4 PubSub-triggered fetch request";
    serviceConfig.Type = "oneshot";
    script = ''
      touch /shared/pubsub-fetch-triggered
    '';
  };

  services.kubo = lib.mkIf usesKubo {
    enable = true;
    dataDir = if role == "pubsub" then "/shared/pubsub-follower-repo" else "/shared/ipfs-repo";
    localDiscovery = false;
    user = "root";
    group = "root";
    settings.Pubsub.Enabled = role == "pubsub";
  };

  systemd.services.ipfs = lib.mkIf usesKubo {
    after = [ "shared.mount" ];
    requires = [ "shared.mount" ];
    environment = {
      IPFS_TELEMETRY = "off";
      XDG_CONFIG_HOME = if role == "pubsub" then "/shared/pubsub-follower-xdg" else "/shared/ipfs-xdg";
    };
  };

  microvm = {
    hypervisor = "qemu";
    vcpu = 1;
    mem = if role == "pubsub" then 768 else 384;
    interfaces = [
      {
        type = "user";
        id = "qemu";
        mac =
          if role == "leader-a" then
            "02:00:00:00:00:0a"
          else if role == "leader-b" then
            "02:00:00:00:00:0b"
          else if role == "ipfs-publisher" then
            "02:00:00:00:00:0d"
          else if role == "ipfs-follower" then
            "02:00:00:00:00:0e"
          else if role == "pubsub" then
            "02:00:00:00:00:0f"
          else
            "02:00:00:00:00:0c";
      }
    ];
    shares = [
      {
        tag = "ro-store";
        source = "/nix/store";
        mountPoint = "/nix/.ro-store";
        readOnly = true;
      }
      {
        tag = "shared";
        source = "/tmp/cluster-identity-microvm";
        mountPoint = "/shared";
        readOnly = false;
      }
    ];
  };

  boot.kernelParams = [
    "console=ttyS0"
    "quiet"
    "systemd.show_status=auto"
  ];
  services.getty.autologinUser = lib.mkForce null;
}
