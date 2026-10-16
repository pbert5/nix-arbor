{ pkgs, ... }:
{
  # Runtime credentials are generated on the host and persisted root-only.
  # Only their fixed source paths enter the Nix closure.
  systemd.services.arbor-oci-auth = {
    description = "Restore private OCI htpasswd files into /run before nginx";
    wantedBy = [ "multi-user.target" ];
    before = [ "nginx.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      set -eu
      source=/var/lib/arbor-secrets/private-oci-registry
      target=/run/secrets/private-oci-registry
      test -s "$source/pull.htpasswd"
      test -s "$source/push.htpasswd"
      ${pkgs.coreutils}/bin/install -d -m 0750 -o root -g nginx "$target"
      ${pkgs.coreutils}/bin/install -m 0640 -o root -g nginx "$source/pull.htpasswd" "$target/pull.htpasswd"
      ${pkgs.coreutils}/bin/install -m 0640 -o root -g nginx "$source/push.htpasswd" "$target/push.htpasswd"
    '';
  };
  systemd.services.nginx = {
    requires = [ "arbor-oci-auth.service" ];
    after = [ "arbor-oci-auth.service" ];
  };
}
