{ pkgs }:
pkgs.testers.runNixOSTest {
  name = "private-oci-registry";

  nodes.machine =
    { ... }:
    let
      tailscaleMock =
        pkgs.runCommand "tailscale-cli-mock"
          {
            meta.mainProgram = "tailscale";
          }
          ''
            mkdir -p $out/bin
            cat > $out/bin/tailscale <<'EOF'
            #!/bin/sh
            case "$*" in
              "serve --https=443 --bg http://127.0.0.1:5101"|\
              "serve --https=8443 --bg http://127.0.0.1:5102"|\
              "serve --https=8443 --yes off"|\
              "serve --https=443 --yes off")
                printf '%s\n' "$*" >> /run/tailscale-cli-mock.log
                ;;
              *)
                echo "unexpected tailscale arguments: $*" >&2
                exit 2
                ;;
            esac
            EOF
            chmod +x $out/bin/tailscale
          '';
    in
    {
      imports = [ ../config/modules/private-oci-registry.nix ];
      arbor.ci.privateRegistry.enable = true;

      services.tailscale.enable = true;
      services.tailscale.package = tailscaleMock;
      systemd.services.tailscaled.wantedBy = pkgs.lib.mkForce [ ];
      systemd.services.tailscale-oci-registry-serve = {
        wantedBy = pkgs.lib.mkForce [ ];
        requires = pkgs.lib.mkForce [ "nginx.service" ];
        after = pkgs.lib.mkForce [ "nginx.service" ];
      };

      systemd.services.zfs-import-mypool = {
        serviceConfig.Type = "oneshot";
        script = "true";
      };
      systemd.services.zfs-mount = {
        serviceConfig.Type = "oneshot";
        script = "true";
      };

      systemd.services.private-oci-registry-test-secrets = {
        before = [ "nginx.service" ];
        requiredBy = [ "nginx.service" ];
        serviceConfig.Type = "oneshot";
        script = ''
          install -d -o nginx -g nginx -m 0750 /run/secrets/private-oci-registry
          ${pkgs.apacheHttpd}/bin/htpasswd -B -bc /run/secrets/private-oci-registry/pull.htpasswd reader test-pull
          ${pkgs.apacheHttpd}/bin/htpasswd -B -bc /run/secrets/private-oci-registry/push.htpasswd writer test-push
          chown nginx:nginx /run/secrets/private-oci-registry/*.htpasswd
          chmod 0640 /run/secrets/private-oci-registry/*.htpasswd
        '';
      };

      environment.systemPackages = [
        pkgs.curl
        pkgs.python3
      ];
      networking.firewall.enable = false;
    };

  testScript = ''
    import textwrap

    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("mkdir -p /mypool")
    machine.fail("systemctl start private-oci-registry-storage.service")
    machine.succeed("mount -t tmpfs -o mode=0755 tmpfs /mypool")
    machine.succeed("systemctl start private-oci-registry-storage.service")
    machine.succeed("systemctl start docker-registry.service nginx.service")
    machine.succeed("systemctl start tailscale-oci-registry-serve.service")
    machine.succeed("systemctl stop tailscale-oci-registry-serve.service")
    machine.succeed("grep -Fx 'serve --https=443 --bg http://127.0.0.1:5101' /run/tailscale-cli-mock.log")
    machine.succeed("grep -Fx 'serve --https=8443 --bg http://127.0.0.1:5102' /run/tailscale-cli-mock.log")
    machine.succeed("grep -Fx 'serve --https=8443 --yes off' /run/tailscale-cli-mock.log")
    machine.succeed("grep -Fx 'serve --https=443 --yes off' /run/tailscale-cli-mock.log")
    machine.wait_for_open_port(5101)
    machine.wait_for_open_port(5102)
    machine.succeed("ss -lnt | grep -F '127.0.0.1:5100'")
    machine.succeed("ss -lnt | grep -F '127.0.0.1:5101'")
    machine.succeed("ss -lnt | grep -F '127.0.0.1:5102'")
    machine.fail("ss -lnt | grep -E '0.0.0.0:(5100|5101|5102)'")

    machine.succeed("curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:5101/v2/ | grep -qx 401")
    machine.succeed("curl --silent --output /dev/null --write-out '%{http_code}' --user reader:test-pull http://127.0.0.1:5101/v2/ | grep -qx 200")
    machine.succeed("curl --silent --output /dev/null --write-out '%{http_code}' --user reader:test-pull --request POST http://127.0.0.1:5101/v2/ci/test/blobs/uploads/ | grep -qx 403")
    machine.succeed("curl --silent --output /dev/null --write-out '%{http_code}' --user writer:test-push http://127.0.0.1:5101/v2/ | grep -qx 401")
    machine.succeed("curl --silent --output /dev/null --write-out '%{http_code}' --user reader:test-pull http://127.0.0.1:5102/v2/ | grep -qx 401")

    machine.succeed(textwrap.dedent(r"""
      python3 - <<'PY'
      import base64, hashlib, json, urllib.error, urllib.parse, urllib.request

      root = 'http://127.0.0.1:5102/v2/ci/test'
      reader = 'http://127.0.0.1:5101/v2/ci/test'
      writer_auth = 'Basic ' + base64.b64encode(b'writer:test-push').decode()
      reader_auth = 'Basic ' + base64.b64encode(b'reader:test-pull').decode()

      def request(url, method='GET', body=None, auth=writer_auth, headers=None):
          req_headers = {'Authorization': auth}
          req_headers.update(headers or {})
          req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
          with urllib.request.urlopen(req) as response:
              return response.status, response.headers, response.read()

      def upload(data, media_type):
          status, headers, _ = request(root + '/blobs/uploads/', 'POST')
          assert status == 202
          location = urllib.parse.urljoin(root + '/blobs/uploads/', headers['Location'])
          digest = 'sha256:' + hashlib.sha256(data).hexdigest()
          url = location + ('&' if '?' in location else '?') + 'digest=' + urllib.parse.quote(digest)
          status, _, _ = request(url, 'PUT', data, headers={'Content-Type': media_type})
          assert status == 201
          return digest, len(data)

      config = json.dumps({'architecture': 'amd64', 'os': 'linux', 'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + hashlib.sha256(b'layer').hexdigest()]}}).encode()
      layer = b'layer'
      config_digest, config_size = upload(config, 'application/octet-stream')
      layer_digest, layer_size = upload(layer, 'application/octet-stream')
      manifest = json.dumps({
          'schemaVersion': 2,
          'mediaType': 'application/vnd.oci.image.manifest.v1+json',
          'config': {'mediaType': 'application/vnd.oci.image.config.v1+json', 'digest': config_digest, 'size': config_size},
          'layers': [{'mediaType': 'application/vnd.oci.image.layer.v1.tar', 'digest': layer_digest, 'size': layer_size}],
      }).encode()
      manifest_type = 'application/vnd.oci.image.manifest.v1+json'
      status, pushed, _ = request(root + '/manifests/immutable-test-commit', 'PUT', manifest, headers={'Content-Type': manifest_type})
      assert status == 201
      digest = pushed['Docker-Content-Digest']

      status, pulled, pulled_manifest = request(reader + '/manifests/' + digest, auth=reader_auth, headers={'Accept': manifest_type})
      assert status == 200 and pulled['Docker-Content-Digest'] == digest and pulled_manifest == manifest
      status, _, pulled_layer = request(reader + '/blobs/' + layer_digest, auth=reader_auth)
      assert status == 200 and pulled_layer == layer

      try:
          request(reader + '/manifests/' + digest, 'DELETE', auth=reader_auth)
          raise AssertionError('pull-only credential was allowed to delete a manifest')
      except urllib.error.HTTPError as error:
          assert error.code == 403
      with open('/tmp/expected-registry-digest', 'w') as expected:
          expected.write(digest)
      print(digest)
      PY
    """))
    machine.succeed("systemctl restart docker-registry.service nginx.service")
    machine.succeed(textwrap.dedent(r"""
      python3 - <<'PY'
      import base64, urllib.request
      auth = 'Basic ' + base64.b64encode(b'reader:test-pull').decode()
      url = 'http://127.0.0.1:5101/v2/ci/test/manifests/immutable-test-commit'
      request = urllib.request.Request(url, headers={'Authorization': auth, 'Accept': 'application/vnd.oci.image.manifest.v1+json'}, method='HEAD')
      with urllib.request.urlopen(request) as response:
          assert response.status == 200
          with open('/tmp/expected-registry-digest') as expected:
              assert response.headers['Docker-Content-Digest'] == expected.read()
      PY
    """))
    machine.succeed("systemctl stop nginx.service docker-registry.service")
    machine.succeed("systemctl start private-oci-registry-gc-dry-run.service")
    machine.succeed("systemctl start docker-registry.service nginx.service")
    machine.succeed("systemctl is-active docker-registry.service nginx.service")
    machine.wait_for_open_port(5101)
    machine.succeed("curl --fail --silent --head --user reader:test-pull --header 'Accept: application/vnd.oci.image.manifest.v1+json' http://127.0.0.1:5101/v2/ci/test/manifests/immutable-test-commit")
  '';
}
