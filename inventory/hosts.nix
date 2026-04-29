{
  inputs ? null,
}:
{
  dev-machine = {
    exported = true;
    system = "x86_64-linux";
    roles = [ "workstation" ];
    networks = [
      "privateYggdrasil"
      "tailscale"
    ];
    publicYggdrasil = false;
    dendrites = [
      "media/game-library"
    ];
    fruits = [ ];
    users = [
      "ash"
      "madeline"
    ];
    facts = { };
    org = { };
    hardwareModules =
      if inputs == null || !(inputs ? devMachineHardware) then
        [ ]
      else
        [
          (inputs.devMachineHardware + "/hardware-configuration.nix")
        ];
    overrides = [ "dev-machine" ];
  };

  "r640-0" = {
    exported = true;
    system = "x86_64-linux";
    roles = [
      "workstation"
      "annex-storage"
      "seaweed-master"
      "seaweed-volume"
      "seaweed-filer"
      "archive-node"
      "radicle-seed"
      "storage-fabric-observer"
    ];
    networks = [
      "privateYggdrasil"
      "tailscale"
    ];
    publicYggdrasil = false;
    dendrites = [
      "media/game-library"
      "system/distributed-builds"
      "storage/zfs"
      "storage/git-annex"
      "storage/seaweedfs-hot"
      "storage/archive"
      "storage/storage-observability"
      "network/radicle"
    ];
    fruits = [ ];
    users = [
      "ash"
      "madeline"
    ];
    facts = {
      hostId = "cbda65de";
      storage.zfs = {
        poolName = "mypool";
        rootMountPoint = "/mypool";
      };
    };
    org.storage.zfs.linkedUsers = [
      "ash"
      "madeline"
    ];
    org.storage.annex = {
      group = "archive";
      archive.nas = {
        enable = true;
        path = "/mypool/annex-archive/nas";
      };
    };
    org.network.radicle = {
      # Generated on first boot by the radicle-keygen systemd oneshot.
      # To re-key: stop radicle-node, delete the file, reboot.
      privateKeyFile = "/var/lib/radicle/keys/radicle";
      repos = [
        "flake-devbox"
        "cluster-data"
      ];
    };
    org.nix = {
      buildMachine = {
        maxJobs = 8;
        speedFactor = 2;
      };
      distributedBuilds = {
        builders = [ "desktoptoodle" ];
        sshKey = "/run/keys/REPLACE_ME";
      };
    };
    hardwareModules = [
      ../modules/_hardware-configs/r640-0-hardware-configuration.nix
    ];
    overrides = [ "r640-0" ];
  };

  desktoptoodle = {
    exported = true;
    system = "x86_64-linux";
    roles = [
      "workstation"
      "annex-storage"
      "seaweed-volume"
      "seaweed-filer"
      "archive-node"
      "radicle-seed"
      "storage-fabric-observer"
    ];
    networks = [
      "privateYggdrasil"
      "tailscale"
    ];
    publicYggdrasil = false;
    dendrites = [
      "desktop/gnome"
      "media/game-library"
      "system/distributed-builds"
      "system/workstation/gaming"
      "storage/git-annex"
      "storage/seaweedfs-hot"
      "storage/archive"
      "storage/storage-observability"
      "storage/tape" # here we could also specify which tape library manager we want like "storage/tape/fossilsafe" and then the inventory would just have to specify the settings for that manager, tho this only works if we assume there is a single tape library which is safe
      "network/radicle"
    ];
    fruits = [ "tapelib" ];
    users = [ "ash" ];
    facts.storage.tape.devices = {
      changer = "/dev/tape/by-id/REPLACE_ME";
      drive = "/dev/tape/by-id/REPLACE_ME";
      drives = [
        "/dev/tape/by-id/REPLACE_ME"
        "/dev/tape/by-id/REPLACE_ME"
      ];
    };
    org.storage.tape = {
      manager = "tapelib";
      tapelib = {
        stateDir = "/var/lib/tapelib";
        openFirewall = false;
        games.selectedTapes = [
          # TODO: this should be managed externaly
          "385182L5"
          "430550L5"
          "383685L5"
        ];
      };
    };
    org.storage.annex = {
      group = "archive";
      archive.tape.enable = true;
      # Set after first-boot: run `cat /srv/annex/cluster-data/.ssh/id_ed25519.pub`
      # on desktoptoodle and paste the result here, then redeploy both hosts.
      # sshPublicKey = "ssh-ed25519 AAAA...";
    };
    org.network.radicle = {
      # Generated on first boot by the radicle-keygen systemd oneshot.
      # To re-key: stop radicle-node, delete the file, reboot.
      privateKeyFile = "/var/lib/radicle/keys/radicle";
      repos = [
        "flake-devbox"
        "cluster-data"
      ];
    };
    org.nix = {
      buildMachine = {
        maxJobs = 4;
        speedFactor = 1;
      };
      distributedBuilds = {
        builders = [ "r640-0" ];
        sshKey = "/run/keys/REPLACE_ME"; # TODO: this should probobly also be pointed at the root location like how r640-0 is
      };
    };
    hardwareModules = [
      ../modules/_hardware-configs/desktoptoodle-hardware-configuration.nix
    ];
    overrides = [ "desktoptoodle" ];
  };

  compute-worker = {
    exported = false;
    system = "x86_64-linux";
    roles = [ "compute-worker" ];
    networks = [ "privateYggdrasil" ];
    publicYggdrasil = false;
    dendrites = [ ];
    fruits = [ ];
    users = [ ];
    facts = { };
    org = { };
    overrides = [ ];
  };

  # Dell PowerEdge T320 — currently running TrueNAS Scale, being migrated to NixOS.
  # exported = false until NixOS is installed and the hardware config UUID is updated.
  # Hardware: Xeon E5-2470 v2, 94GB RAM, LSI MegaRAID SAS 2008 (JBOD)
  # ZFS: big (mirror 2x10.9TB @ /mnt/big), fast (1TB SSD @ /mnt/fast)
  # Tailscale: 100.64.0.10
  "t320-truenas-scale" = {
    exported = false;
    system = "x86_64-linux";
    roles = [ "compute-worker" ];
    networks = [ "tailscale" ];
    publicYggdrasil = false;
    dendrites = [ "storage/zfs" ];
    fruits = [ ];
    users = [ "ash" ];
    facts = {
      hostId = "21f0da5a";
      storage.zfs = {
        # Primary data pool (mirror). The `fast` pool is added via host override.
        poolName = "big";
        rootMountPoint = "/mnt/big";
      };
    };
    org = { };
    hardwareModules = [
      ../modules/_hardware-configs/t320-truenas-scale-hardware-configuration.nix
    ];
    overrides = [ "t320-truenas-scale" ];
  };
}
