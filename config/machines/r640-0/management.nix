{ config, lib, ... }:
{
  networking.hostName = "r640-0";
  networking.networkmanager = {
    enable = true;
    unmanaged = [ "tailscale0" ];
    ensureProfiles.profiles = {
      eno3 = {
        connection = {
          id = "eno3";
          type = "ethernet";
          interface-name = "eno3";
        };
        ipv4.method = "auto";
        ipv6.method = "auto";
      };
      eno4 = {
        connection = {
          id = "eno4";
          type = "ethernet";
          interface-name = "eno4";
        };
        ipv4.method = "auto";
        ipv6.method = "auto";
      };
    };
  };
  assertions = [
    {
      assertion =
        config.networking.networkmanager.enable
        && !config.networking.useDHCP
        && !config.systemd.network.enable;
      message = "r640-0 physical networking must be managed by NetworkManager";
    }
    {
      assertion =
        lib.all
          (
            interface:
            let
              profile = config.networking.networkmanager.ensureProfiles.profiles.${interface};
            in
            profile.connection.interface-name == interface
            && profile.ipv4.method == "auto"
            && profile.ipv6.method == "auto"
            && !(profile ? ipv4.address1)
            && !(profile.connection ? uuid)
          )
          [
            "eno3"
            "eno4"
          ];
      message = "r640-0 eno3 and eno4 must remain NetworkManager DHCP profiles without static addresses or UUIDs";
    }
    {
      assertion = config.virtualisation.docker.enable;
      message = "r640-0 must preserve Docker capability without selecting workloads";
    }
    {
      assertion = config.networking.networkmanager.unmanaged == [ "tailscale0" ];
      message = "r640-0 must keep tailscale0 outside NetworkManager management";
    }
  ];
  services.tailscale = {
    enable = true;
    useRoutingFeatures = "client";
    extraSetFlags = [ "--accept-dns=false" ];
  };
  # Yggdrasil/Registry are intentionally not imported into this physical
  # profile. Their future overlay must remain optional to these paths.
  systemd.tmpfiles.rules = [
    "z /home/ash 2750 ash home-share - -"
    "z /home/madeline 2750 madeline home-share - -"
  ];
  systemd.services.home-share-flake-link = {
    description = "Create the safe r640 shared flake link";
    wantedBy = [ "multi-user.target" ];
    after = [ "systemd-tmpfiles-setup.service" ];
    serviceConfig.Type = "oneshot";
    script = ''
      set -eu
      destination=/home/madeline/flake
      target=/home/ash/flake
      if [ -L "$destination" ]; then
        [ "$(readlink "$destination")" = "$target" ] || echo "leaving conflicting symlink $destination"
      elif [ -e "$destination" ]; then
        echo "leaving existing path $destination"
      elif [ -d "$target" ]; then
        ln -s "$target" "$destination"
      else
        echo "target $target is not present; leaving homes untouched"
      fi
    '';
  };
}
