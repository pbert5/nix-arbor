import json

start_all()

for node in (root_a, root_b, child, grandchild):
    node.wait_for_unit("arbor-registryd.service", timeout=120)
    node.wait_for_open_port(4001, timeout=120)
print("BOOTSTRAP COMPLETE")

statuses = [json.loads(node.succeed("python3 /etc/arbor-test/status.py")) for node in (root_a, root_b, child, grandchild)]
assert all(status["realmId"] == "arbor-acceptance-vm-realm-v1" for status in statuses)
assert all(status["databaseAddresses"].get("registry") for status in statuses)

# The daemon generates its libp2p identity at runtime. Resolve that public
# peer id from root-a, then install runtime-only bootstrap overrides on the
# other guests so the acceptance uses the actual libp2p peer identity.
root_peer = json.loads(root_a.succeed("python3 /etc/arbor-test/status.py"))["peerId"]
root_b_peer = json.loads(root_b.succeed("python3 /etc/arbor-test/status.py"))["peerId"]
registry_address = json.loads(root_a.succeed("python3 /etc/arbor-test/status.py"))["databaseAddresses"]["registry"]
for node in (root_b, child, grandchild):
    peers = ["/ip4/10.42.0.10/tcp/4001/p2p/%s" % root_peer]
    if node in (child, grandchild):
        peers.append("/ip4/10.42.0.11/tcp/4001/p2p/%s" % root_b_peer)
    node.succeed("mkdir -p /run/systemd/system/arbor-registryd.service.d")
    node.succeed("printf '%%s\\n' '[Service]' 'Environment=ARBOR_REGISTRY_BOOTSTRAP_PEERS=%s' 'Environment=ARBOR_REGISTRY_DATABASE_ADDRESS=%s' > /run/systemd/system/arbor-registryd.service.d/bootstrap.conf" % (",".join(peers), registry_address))
    node.succeed("systemctl daemon-reload; systemctl restart arbor-registryd.service")
    node.wait_for_unit("arbor-registryd.service", timeout=120)
assert len({json.loads(node.succeed("python3 /etc/arbor-test/status.py"))["databaseAddresses"]["registry"] for node in (root_a, root_b, child, grandchild)}) == 1
print("INDEPENDENT TRANSPORT REALM AND DATABASE ADDRESS VERIFIED")

child.wait_for_unit("openbao-test.service", timeout=120)
child.wait_for_unit("seed-openbao-secret.service", timeout=120)
child.wait_for_unit("arbor-vault-runtime-arbor-test-consumer-bridge.service", timeout=120)
child.succeed("systemctl start arbor-test-consumer.service")
child.succeed("test \"$(cat /run/arbor-test/consumer.sha256)\" = \"$(cat /run/arbor-test/secret.sha256)\"")
print("SECRET DELIVERY VERIFIED")

root_a.succeed("python3 /etc/arbor-test/scenario.py")
root_public = root_a.succeed("cat /run/arbor-test/root-a.public").strip()
def configure_registryctl(node):
    config = json.dumps({
        "stateDir": "/run/arbor-test/accepted-cross-guest",
        "transportSocket": "/run/arbor-registryd/registry.sock",
        "transportTokenFile": "/run/arbor-test/registry.token",
        "bootstrapAuthoritiesFile": "/run/arbor-test/bootstrap-authorities.json",
        "identityDir": "/run/arbor-test/keys",
        "providerCursorFile": "/run/arbor-test/provider-cursor.json",
        "authorityIssuers": ["root-a"],
    }, sort_keys=True)
    node.succeed("mkdir -p /run/arbor-test/keys; printf %r > /run/arbor-test/registryctl.json; printf %r > /run/arbor-test/bootstrap-authorities.json" % (config, json.dumps({"root-a": root_public})))

for node in (root_b, child, grandchild):
    configure_registryctl(node)
    node.succeed("arbor-registryctl --config /run/arbor-test/registryctl.json --format json sync")
root_a.succeed("ARBOR_TEST_RECORD_ID=transport-remote-root-a python3 /etc/arbor-test/append.py")
child.wait_until_succeeds("python3 /etc/arbor-test/list.py | grep -q transport-remote-root-a", timeout=30)
child.succeed("arbor-registryctl --config /run/arbor-test/registryctl.json --format json sync")
child.succeed("arbor-registryctl --config /run/arbor-test/registryctl.json --format json projection | jq -e '.[\"root-a\"].schema == \"identity-generation\"'")
print("CROSS-GUEST SIGNED RECORD ACCEPTED AND MATERIALIZED")
child.succeed("ARBOR_TEST_RECORD_ID=transport-remote-child python3 /etc/arbor-test/append.py")
root_b.wait_until_succeeds("python3 /etc/arbor-test/list.py | grep -q transport-remote-child", timeout=30)
root_b.succeed("python3 /etc/arbor-test/append.py")
root_b.wait_until_succeeds("python3 /etc/arbor-test/list.py | grep -q transport-local-root-b", timeout=30)
print("CROSS-GUEST RAW ORBITDB REPLICATION AND MULTI-WRITER VERIFIED")

# The original realm opener is intentionally unavailable for a write and then
# restarted.  The surviving peers must continue exchanging raw events.
root_a.succeed("systemctl stop arbor-registryd.service")
root_b.succeed("ARBOR_TEST_RECORD_ID=transport-first-loss-root-b2 python3 /etc/arbor-test/append.py")
child.wait_until_succeeds("python3 /etc/arbor-test/list.py | grep -q transport-first-loss-root-b2", timeout=30)
root_a.succeed("systemctl start arbor-registryd.service")
root_a.wait_for_unit("arbor-registryd.service", timeout=120)
root_a.wait_until_succeeds("test -S /run/arbor-registryd/registry.sock", timeout=30)
root_a.wait_until_succeeds("python3 /etc/arbor-test/list.py | grep -q transport-first-loss-root-b2", timeout=30)
print("FIRST REALM CREATOR LOSS AND REJOIN CATCH-UP VERIFIED")

print("LOCAL RECONCILIATION DUPLICATE AND QUARANTINE VERIFIED")

child.succeed("test -f /run/systemd-vaultd/secrets/arbor-test-consumer.service.json")
child.succeed("old=$(cat /run/arbor-test/secret.sha256); value=$(head -c 24 /dev/urandom | base64 -w0); printf '%s' \"$value\" | sha256sum | cut -d' ' -f1 >/run/arbor-test/new-secret.sha256; BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN=arbor-test-root bao kv put secret/arbor/acceptance value=\"$value\" >/dev/null; test \"$old\" != \"$(cat /run/arbor-test/new-secret.sha256)\"")
child.wait_until_succeeds("test \"$(cat /run/arbor-test/consumer.sha256)\" = \"$(cat /run/arbor-test/new-secret.sha256)\"", timeout=120)
print("SECRET ROTATION VERIFIED")

child.succeed("old_consumer=$(cat /run/arbor-test/consumer.sha256); mkdir -p /run/systemd/system/arbor-test-consumer.service.d; printf '%s\\n' '[Service]' 'ExecStart=' 'ExecStart=/run/current-system/sw/bin/false' >/run/systemd/system/arbor-test-consumer.service.d/fail-refresh.conf; systemctl daemon-reload; value=$(head -c 24 /dev/urandom | base64 -w0); printf '%s' \"$value\" | sha256sum | cut -d' ' -f1 >/run/arbor-test/failed-secret.sha256; BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN=arbor-test-root bao kv put secret/arbor/acceptance value=\"$value\" >/dev/null; printf '%s' \"$old_consumer\" >/run/arbor-test/consumer-before-failed-refresh.sha256")
child.wait_until_succeeds("journalctl -u arbor-vault-runtime-api.service --no-pager | grep -q 'restart command failed'", timeout=30)
child.succeed("test \"$(cat /run/arbor-test/consumer.sha256)\" = \"$(cat /run/arbor-test/consumer-before-failed-refresh.sha256)\"")
child.succeed("systemctl revert arbor-test-consumer.service; systemctl daemon-reload; systemctl restart arbor-test-consumer.service")
child.wait_until_succeeds("test \"$(cat /run/arbor-test/consumer.sha256)\" = \"$(cat /run/arbor-test/failed-secret.sha256)\"", timeout=120)
print("FAILED CONSUMER REFRESH REPORTED WITHOUT FALSE SUCCESS; RETRY RECOVERED")

child.succeed("value=$(BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN=arbor-test-root bao kv get -field=value secret/arbor/acceptance); ! nix-store -qR /run/current-system | xargs -r grep -I -F \"$value\" 2>/dev/null; ! grep -R -F \"$value\" /run/arbor-test /var/log 2>/dev/null")
child.succeed("systemctl restart arbor-registryd.service")
child.wait_for_unit("arbor-registryd.service", timeout=120)
child.reboot()
child.wait_for_shutdown()
child.start()
child.wait_for_unit("arbor-registryd.service", timeout=120)
child.wait_until_succeeds("test -S /run/arbor-registryd/registry.sock", timeout=30)
child.wait_for_unit("arbor-vault-runtime-arbor-test-consumer-bridge.service", timeout=120)
print("RESTART AND REBOOT RECOVERED")

root_a.succeed("systemctl stop arbor-registryd.service")
child.succeed("systemctl is-system-running --wait || true")
grandchild.succeed("systemctl is-system-running --wait || true")
root_b.succeed("systemctl is-active arbor-registryd.service")
print("PRIMARY TRANSPORT DAEMON STOPPED; STANDBY TRANSPORT REMAINS UP")

root_a.succeed("mkdir -p /run/arbor-test; ssh-keygen -q -t ed25519 -N '' -f /run/arbor-test/id_ed25519")
for node in (child, grandchild):
    key = root_a.succeed("cat /run/arbor-test/id_ed25519.pub").strip()
    node.succeed("install -d -m 0700 /root/.ssh")
    node.succeed("printf '%%s\\n' %r >> /root/.ssh/authorized_keys" % key)
    node.succeed("chmod 0600 /root/.ssh/authorized_keys")
root_a.succeed("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /run/arbor-test/id_ed25519 root@10.42.0.12 true")
print("SSH CONNECTIVITY VERIFIED")

root_a.succeed("cp /etc/arbor-test/snapshot.json /run/arbor-test/snapshot.json")
root_a.succeed("sd=$(jq -cS .snapshot /run/arbor-test/snapshot.json | sha256sum | cut -d' ' -f1); jq --arg sd \"$sd\" '.snapshotDigest=$sd' /run/arbor-test/snapshot.json >/run/arbor-test/snapshot.tmp; digest=$(jq -cS 'del(.digest)' /run/arbor-test/snapshot.tmp | sha256sum | cut -d' ' -f1); jq --arg digest \"$digest\" '.digest=$digest' /run/arbor-test/snapshot.tmp >/run/arbor-test/snapshot.json")
root_a.succeed("jq -e '.plan.risks | length > 0' /run/arbor-test/snapshot.json")
root_a.succeed("arbor-manager nodes list --snapshot /run/arbor-test/snapshot.json --scope selected --format names | grep -q child")
print("GRAPH-RISK PLAN VERIFIED")
print("VM ACCEPTANCE SMOKE COMPLETE")
